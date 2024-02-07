from flask import Flask, render_template, send_from_directory, request
from werkzeug.middleware.proxy_fix import ProxyFix
from markupsafe import escape, Markup
import os
import re
import json
from datetime import datetime

DATA_DIR = '/var/opt/pnlogger/' if os.name == 'posix' else '../var/'

LOG_DIR = os.path.join(DATA_DIR, 'data')
CONFIG_DIR = os.path.join(DATA_DIR, 'variables')

app = Flask('DAQhub', static_folder='../www/assets', template_folder='../www/templates')

@app.route("/")
def home():
    return render_template('root.html')
    
@app.route("/status")
def status():
    import subprocess
    
    try:
        output = subprocess.run(['systemctl','status','pnlogger','--lines','48'], capture_output=True)
    except FileNotFoundError:
        return render_template('status.html', pnloggerservice='systemctl not available. Is the server in the right environment?')
    
    return render_template('status.html', pnloggerservice=output.stdout.decode())
    
@app.route("/config")
def config_list():
    configs = []
    
    try:
        for dirent in os.scandir(CONFIG_DIR):
            if dirent.is_file():
                res = re.fullmatch(r'dataconfig(\d+).txt', dirent.name)
                if res:
                    stat = dirent.stat()
                    mtime = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M')
                    configs.append({'id':res[1],'file':res[0],'mtime':mtime})
    except FileNotFoundError:
        pass
                
    configs.sort(key=lambda cfg: cfg['id'])
    
    nextid = 1
    if len(configs):
        nextid = int(configs[-1]['id'])+1
                
    return render_template('config_list.html', configs=configs, next=nextid)
    
@app.get("/config/<int:id>")
def config_form(id):
    exists = True
    try:
        variables, description = readconfig(f'dataconfig{id}.txt')
    except FileNotFoundError:
        # this is new, read prior as basis
        exists = False
        description = ''
        try:
            variables = readconfig(f'dataconfig{id-1}.txt')[0]
        except FileNotFoundError:
            # if you enter something bigger directly into the URL, it's your problem
            variables = []
        
    rowdata = map(lambda x: Markup(json.dumps(x)), variables)
    return render_template('config.html', exists=exists, id=id, variables=rowdata, description=description)
    
@app.post("/config/<int:id>")
def config_update(id):
    variables = json.loads(request.form['variables'])
    
    configpath = os.path.join(CONFIG_DIR, f'dataconfig{id}.txt')
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(configpath, 'w') as conffile:
        for var in variables:
            conffile.write(f"{var['type']},{var['byteaddress']},{var['title']}\n")
        conffile.write("\n")
        conffile.write(request.form['description'])
    
    response = {
        'request': request.form
    }
    
    return json.dumps(response)

@app.route("/logs")
def list_files():
    files = []
    dirs = []
    
    try:
        for dirent in os.scandir(LOG_DIR):
            if dirent.is_file():
                res = re.fullmatch(r'(\d{4})(\d{2})(\d{2}).tgz', dirent.name)
                if res and int(res[2]) <= 12 and int(res[3]) <= 31:
                    files.append(fileentry(None, dirent))
            if dirent.is_dir():
                res = re.fullmatch(r'(\d{4})(\d{2})(\d{2})', dirent.name)
                if res and int(res[2]) <= 12 and int(res[3]) <= 31:
                    dirs.append(dirent.name)
                    
        for dir in dirs:
            for dirent in os.scandir(os.path.join(LOG_DIR, dir)):
                if dirent.is_file():
                    files.append(fileentry(dir, dirent))
    except FileNotFoundError:
        pass
                
    files.sort(key=lambda f: f['link'], reverse=True)
    return render_template('files.html', files=files)

def fileentry(dirname, dirent):
    statres = dirent.stat()
    size = f'{statres.st_size/1048576:.1f} MB'
    # statres.st_mtime for modification time...
    # not so useful so long as the timeframe is in the name
    
    date = dirname if dirname else dirent.name[0:8]
    date = f'{date[0:4]}-{date[4:6]}-{date[6:8]}'
    prefix = dirname+'/' if dirname else ''
    
    return {
        'date': date,
        'title': dirent.name,
        'link': prefix + dirent.name,
        'size': size
    }

# nginx should handle these routes directly,
# but these are backup / for development
@app.route("/files/data/<path:name>")
def download_log(name):
    return send_from_directory(LOG_DIR, name, as_attachment=True)
    
@app.route("/files/variables/<name>")
def download_config(name):
    return send_from_directory(CONFIG_DIR, name, as_attachment=True)

def readconfig(fname):
    variables = []
    description = ''
    reading_desc = False
    
    with open(os.path.join(CONFIG_DIR, fname), 'r') as conffile:
        for line in conffile:
            if not reading_desc and line == '\n':
                reading_desc = True
                continue
            
            if reading_desc:
                description += line
            else:
                parts = line.strip().split(',')
                
                addr = parts[1].split('.')
                if len(addr) == 1:
                    addr.append('0')
                
                variables.append({'title':parts[2], 'type':parts[0], 'address':8*int(addr[0])+int(addr[1])})
    return variables, description

# include ewon proxy too?
app.wsgi_app = ProxyFix(
    app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
)
