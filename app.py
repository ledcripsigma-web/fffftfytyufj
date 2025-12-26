from flask import Flask, request, jsonify, render_template_string
import os, zipfile, subprocess, shutil, json, uuid, threading, time

app = Flask(__name__)

# Папки на Render
UPLOADS = '/var/data/uploads' if os.path.exists('/var/data/uploads') else 'uploads'
PROJECTS = '/var/data/projects' if os.path.exists('/var/data/projects') else 'projects'
DB_FILE = 'hosts.json'

os.makedirs(UPLOADS, exist_ok=True)
os.makedirs(PROJECTS, exist_ok=True)

processes = {}

HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>🐍 Python Host</title>
    <style>
        body{background:#0d1117;color:#c9d1d9;font-family:Arial;padding:20px;}
        .box{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:20px;margin:20px 0;max-width:600px;}
        input,button{padding:10px;margin:5px 0;width:100%;border-radius:6px;}
        input{background:#0d1117;border:1px solid #30363d;color:white;}
        button{background:#238636;color:white;border:none;cursor:pointer;}
        .host{background:#21262d;padding:15px;margin:10px 0;border-left:4px solid #58a6ff;}
        .status{padding:3px 10px;border-radius:4px;font-size:12px;margin-left:10px;}
        .running{background:#238636;}.stopped{background:#da3633;}
    </style>
</head>
<body>
    <div style="max-width:800px;margin:0 auto;">
        <h1>🐍 Python Host (Render)</h1>
        
        <div class="box">
            <h3>📤 Upload ZIP + Command</h3>
            <input type="file" id="file" accept=".zip"><br>
            <input type="text" id="command" placeholder="python bot.py" value="python main.py"><br>
            <button onclick="upload()">🚀 Start Hosting</button>
        </div>
        
        <div id="hosts"></div>
    </div>
    
    <script>
    async function upload(){
        let file=document.getElementById('file').files[0];
        let cmd=document.getElementById('command').value.trim();
        if(!file){alert('Select ZIP');return}
        if(!file.name.endsWith('.zip')){alert('Only ZIP');return}
        if(!cmd){alert('Enter command');return}
        
        let form=new FormData();
        form.append('file',file);
        form.append('command',cmd);
        
        let res=await fetch('/upload',{method:'POST',body:form});
        let data=await res.json();
        if(data.success){
            alert('✅ Project started!');
            document.getElementById('file').value='';
            load();
        }else alert('❌ Error: '+data.error);
    }
    
    async function load(){
        let res=await fetch('/hosts');
        let hosts=await res.json();
        let html='<div class="box"><h3>📁 Active Projects</h3>';
        if(hosts.length==0) html+='<p>No projects</p>';
        else hosts.forEach(h=>{
            html+=`<div class="host">
                <b>${h.name}</b><span class="status ${h.status}">${h.status}</span><br>
                <code>${h.command}</code><br>
                <button onclick="control('${h.id}','stop')">⏹️ Stop</button>
                <button onclick="control('${h.id}','start')">▶️ Start</button>
                <button onclick="del('${h.id}')" style="background:#da3633">🗑️ Delete</button>
            </div>`;
        });
        html+='</div>';
        document.getElementById('hosts').innerHTML=html;
    }
    
    async function control(id,action){
        await fetch(`/${id}/${action}`,{method:'POST'});
        load();
    }
    
    async function del(id){
        if(confirm('Delete?')){
            await fetch(`/${id}/delete`,{method:'POST'});
            load();
        }
    }
    
    setInterval(load,5000);
    load();
    </script>
</body>
</html>
'''

def load_hosts():
    if os.path.exists(DB_FILE):
        with open(DB_FILE,'r') as f:
            return json.load(f)
    return []

def save_hosts(hosts):
    with open(DB_FILE,'w') as f:
        json.dump(hosts,f,indent=2)

@app.route('/')
def home():
    return render_template_string(HTML)

@app.route('/upload',methods=['POST'])
def upload():
    try:
        file=request.files['file']
        cmd=request.form['command'].strip()
        pid=str(uuid.uuid4())[:8]
        
        # Save ZIP
        zip_path=os.path.join(UPLOADS,f'{pid}_{file.filename}')
        file.save(zip_path)
        
        # Extract
        project_dir=os.path.join(PROJECTS,pid)
        os.makedirs(project_dir)
        with zipfile.ZipFile(zip_path,'r') as z:
            z.extractall(project_dir)
        
        # Start process
        proc=subprocess.Popen(cmd.split(),cwd=project_dir)
        processes[pid]=proc
        
        # Save to DB
        host={'id':pid,'name':file.filename,'command':cmd,'status':'running','created':time.ctime()}
        hosts=load_hosts()
        hosts.append(host)
        save_hosts(hosts)
        
        return jsonify({'success':True,'id':pid})
    except Exception as e:
        return jsonify({'success':False,'error':str(e)})

@app.route('/hosts')
def get_hosts():
    hosts=load_hosts()
    for h in hosts:
        pid=h['id']
        if pid in processes:
            h['status']='running' if processes[pid].poll() is None else 'stopped'
        else:
            h['status']='stopped'
    save_hosts(hosts)
    return jsonify(hosts)

@app.route('/<pid>/<action>',methods=['POST'])
def control(pid,action):
    try:
        if action=='stop':
            if pid in processes:
                processes[pid].terminate()
                del processes[pid]
        elif action=='start':
            hosts=load_hosts()
            host=next((h for h in hosts if h['id']==pid),None)
            if host:
                project_dir=os.path.join(PROJECTS,pid)
                proc=subprocess.Popen(host['command'].split(),cwd=project_dir)
                processes[pid]=proc
        
        # Update status
        hosts=load_hosts()
        for h in hosts:
            if h['id']==pid:
                h['status']='running' if action=='start' else 'stopped'
                break
        save_hosts(hosts)
        return jsonify({'success':True})
    except Exception as e:
        return jsonify({'success':False,'error':str(e)})

@app.route('/<pid>/delete',methods=['POST'])
def delete(pid):
    try:
        if pid in processes:
            processes[pid].terminate()
            del processes[pid]
        
        hosts=[h for h in load_hosts() if h['id']!=pid]
        save_hosts(hosts)
        
        # Clean files
        project_dir=os.path.join(PROJECTS,pid)
        if os.path.exists(project_dir):
            shutil.rmtree(project_dir)
        
        return jsonify({'success':True})
    except:
        return jsonify({'success':False})

if __name__=='__main__':
    app.run(host='0.0.0.0',port=5000)