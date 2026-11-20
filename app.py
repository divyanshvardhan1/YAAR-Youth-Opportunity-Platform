"""Y.A.A.R. academic prototype. Python standard library only; local use."""
import os, re, sqlite3, secrets, hashlib, hmac, math, json, webbrowser, threading
from collections import Counter
from contextlib import contextmanager
from html import escape
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from http.cookies import SimpleCookie
from urllib.parse import urlsplit, parse_qs, urlencode
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = ROOT / 'yaar.db'
# Local: localhost:8765. On Render: 0.0.0.0 and Render's dynamic PORT.
IS_CLOUD = bool(os.environ.get('RENDER_EXTERNAL_URL'))
PORT = int(os.environ.get('PORT', '8765'))
HOST = '0.0.0.0' if os.environ.get('PORT') else '127.0.0.1'
COOKIE_SECURE = '; Secure' if IS_CLOUD else ''

@contextmanager
def database():
    con=sqlite3.connect(DB, timeout=10)
    con.row_factory=sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    try:
        yield con
        con.commit()
    finally:
        con.close()

def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    return salt+'$'+hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),200000).hex()

def verify(password, value):
    return hmac.compare_digest(password_hash(password,value.split('$')[0]),value)

DEMO = [
 ('Weekend Learning Club','Education','teaching, communication, mentoring','Teach basic maths and English to children in a weekend learning club.','Noida','Weekend','On-site',3),
 ('Website for a Social Cause','Technology','coding, html, css, javascript, web development','Build a small accessible website for a community initiative.','Remote','Flexible','Remote',5),
 ('Neighborhood Clean-up','Environment','teamwork, environment, coordination','Help coordinate a community clean-up and recycling awareness drive.','Noida','Weekend','On-site',2),
 ('Creative Stories for Change','Creative','photography, writing, design, social media','Create posters and stories for a youth awareness campaign.','Remote','Flexible','Remote',4),
 ('Digital Literacy Workshop','Education','teaching, coding, communication, computer','Help learners practice basic computer and internet skills.','Greater Noida','Weekend','On-site',3),
 ('Community Event Support','Community','communication, teamwork, event management','Support registration and coordination at a community event.','Delhi','Weekday','On-site',4),
 ('Data Skills for Good','Technology','python, excel, data analysis, coding','Organize sample survey data for a community research exercise.','Remote','Flexible','Remote',4),
 ('Peer Career Mentoring','Skills','mentoring, communication, career guidance','Help students prepare resumes and practice interview skills.','Remote','Weekend','Remote',2),
]

def init_db():
    with database() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT NOT NULL,email TEXT NOT NULL UNIQUE,password TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('youth','ngo')),skills TEXT DEFAULT '',interests TEXT DEFAULT '',location TEXT DEFAULT '',availability TEXT DEFAULT 'Flexible');
        CREATE TABLE IF NOT EXISTS opportunities(id INTEGER PRIMARY KEY, ngo_id INTEGER NOT NULL REFERENCES users(id),title TEXT NOT NULL,category TEXT NOT NULL,skills TEXT NOT NULL,description TEXT NOT NULL,location TEXT NOT NULL,availability TEXT NOT NULL,mode TEXT NOT NULL,hours INTEGER NOT NULL CHECK(hours>0),created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS applications(id INTEGER PRIMARY KEY,youth_id INTEGER NOT NULL REFERENCES users(id),opportunity_id INTEGER NOT NULL REFERENCES opportunities(id),status TEXT NOT NULL DEFAULT 'Pending' CHECK(status IN ('Pending','Accepted','Rejected','Completed')),created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,UNIQUE(youth_id,opportunity_id));
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),expires INTEGER NOT NULL);
        ''')
        if not c.execute('SELECT 1 FROM users WHERE email=?',('ngo@yaar.demo',)).fetchone():
            n=c.execute('INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)',('Community Lab (Demo)','ngo@yaar.demo',password_hash('Demo@123'),'ngo')).lastrowid
            c.execute('INSERT INTO users(name,email,password,role,skills,interests,location,availability) VALUES(?,?,?,?,?,?,?,?)',('Demo Student','youth@yaar.demo',password_hash('Demo@123'),'youth','teaching, coding, communication','education, volunteering','Noida','Weekend'))
            c.executemany('INSERT INTO opportunities(ngo_id,title,category,skills,description,location,availability,mode,hours) VALUES(?,?,?,?,?,?,?,?,?)',[(n,*row) for row in DEMO])

STOP=set('a an the and or to of for in on with is are at as be by from our your help'.split())
def tokens(text):
    return [t for t in re.findall(r'[a-z0-9+#]+',text.lower()) if t not in STOP]

def recommend(user, opportunities):
    """Content-based ranking: smoothed TF-IDF and cosine; preference bonuses."""
    profile = f"{user['skills']} {user['interests']}"
    docs=[tokens(profile)]+[tokens(f"{o['title']} {o['category']} {o['skills']} {o['description']}") for o in opportunities]
    df=Counter(t for d in docs for t in set(d)); n=len(docs)
    def vector(d):
        return {t: k*(math.log((1+n)/(1+df[t]))+1) for t,k in Counter(d).items()}
    def cosine(a,b):
        norm=math.sqrt(sum(v*v for v in a.values())*sum(v*v for v in b.values()))
        return sum(v*b.get(t,0) for t,v in a.items())/norm if norm else 0
    a=vector(docs[0]); ranked=[]
    for o,d in zip(opportunities,docs[1:]):
        c=cosine(a,vector(d))
        location=bool(user['location'].strip()) and (o['mode']=='Remote' or user['location'].strip().casefold()==o['location'].strip().casefold())
        time=bool(user['availability']) and (user['availability']=='Flexible' or o['availability']=='Flexible' or user['availability']==o['availability'])
        score=round(100*(.8*c+.1*location+.1*time)) if docs[0] else 0
        overlap=sorted(set(docs[0]) & set(tokens(o['skills']+' '+o['category'])))
        reasons=[]
        if overlap: reasons.append('Shared terms: '+', '.join(overlap))
        if location: reasons.append('Location / remote preference fits')
        if time: reasons.append('Availability fits')
        if not reasons: reasons=['Limited explicit overlap; review the description']
        ranked.append((o,score,' · '.join(reasons),c))
    return sorted(ranked,key=lambda x:(-x[1],-x[3],x[0]['id']))

def e(value): return escape(str(value if value is not None else ''),quote=True)
def options(items,selected=''): return ''.join(f'<option value="{e(x)}"'+(' selected' if x==selected else '')+f'>{e(x)}</option>' for x in items)
def field(label,name,value='',typ='text',required=True,placeholder=''):
    return f'<label>{e(label)}<input name="{e(name)}" type="{e(typ)}" value="{e(value)}" placeholder="{e(placeholder)}"'+(' required' if required else '')+' maxlength="180"></label>'
def select(label,name,items,selected=''):
    return f'<label>{e(label)}<select name="{e(name)}">{options(items,selected)}</select></label>'
def text_area(label,name,value='',placeholder=''):
    return f'<label>{e(label)}<textarea required name="{e(name)}" maxlength="1500" placeholder="{e(placeholder)}">{e(value)}</textarea></label>'
def hidden(name,value): return f'<input type="hidden" name="{e(name)}" value="{e(value)}">'
def form(action,body,token): return f'<form method="post" action="{action}">{hidden("csrf",token)}{body}</form>'
def badge(status): return f'<span class="badge {e(status.lower())}">{e(status)}</span>'
def button(label,cls=''): return f'<button class="btn {cls}" type="submit">{e(label)}</button>'
def empty(text): return f'<div class="empty">{e(text)}</div>'
def page(title,body,user=None,msg='',error=False,token=''):
    nav='<a href="/">Home</a><a href="/login">Sign in</a><a class="navcta" href="/register">Join Y.A.A.R.</a>'
    if user:
        nav=('<a href="/dashboard">Dashboard</a>'+('<a href="/profile">My profile</a><a href="/applications">Applications</a>' if user['role']=='youth' else '<a href="/post">Post opportunity</a><a href="/applications">Applicants</a>')+form('/logout',button('Sign out','small outline'),token))
    notice=f'<div class="notice {"error" if error else ""}">{e(msg)}</div>' if msg else ''
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(title)} | Y.A.A.R.</title><link rel="stylesheet" href="/static/style.css"></head><body><header><div class="nav"><a class="brand" href="/"><span class="logo">Y<span>.</span></span><span>Y.A.A.R.<small>TURNING POTENTIAL INTO PURPOSE</small></span></a><nav>{nav}</nav></div></header><main>{notice}{body}</main><footer><strong>Y.A.A.R.</strong> · B.Tech CSE Mini Project · KCC ITM · Academic prototype with fictional demo data. <span>Not a live NGO service.</span></footer></body></html>'''

def hero():
    return '''<section class="hero"><div><span class="eyebrow">YOUTH • COMMUNITY • IMPACT</span><h1>Turn your potential<br>into <em>purpose.</em></h1><p>Discover volunteering, community projects and skill-building opportunities that match what you care about and what you can do.</p><div class="actions"><a class="btn" href="/register">Get started →</a><a class="btn outline" href="/login">Explore demo</a></div><div class="hero-note">Youth Activity, Assistance &amp; Redirection</div></div><div class="hero-art"><div class="art-top"><span class="spark">✦</span> YOUR NEXT OPPORTUNITY</div><div class="art-card"><span class="category">EDUCATION</span><h3>Weekend Learning Club</h3><p>Make a difference through teaching.</p><div class="bar"><i style="width:82%"></i></div><small>Illustrative match score • 82%</small></div><div class="art-card second"><span class="category">TECHNOLOGY</span><h3>Build for a social cause</h3><p>Put your coding skills into action.</p><div class="art-meta">Remote · Flexible</div></div></div></section><section class="section"><div class="section-head"><span class="eyebrow">HOW IT WORKS</span><h2>Three steps to meaningful action.</h2></div><div class="three"><article class="panel"><div class="step">01</div><h3>Tell us about yourself</h3><p>Add your skills, interests and availability.</p></article><article class="panel"><div class="step">02</div><h3>Find your match</h3><p>Get ranked opportunities using content-based recommendations.</p></article><article class="panel"><div class="step">03</div><h3>Take action</h3><p>Apply, track your status and build experience.</p></article></div></section>'''

def opportunity_card(o,score,why,applied,token):
    status=applied.get(o['id']); action=badge(status) if status else form('/apply',hidden('opportunity_id',o['id'])+button('Apply now','small'),token)
    return f'''<article class="panel opportunity"><div class="card-top"><span class="category">{e(o['category'])}</span><span class="score">{score}% match</span></div><h3>{e(o['title'])}</h3><div class="muted">{e(o['org'])}</div><p>{e(o['description'])}</p><div class="chips"><span>{e(o['location'])}</span><span>{e(o['availability'])}</span><span>{e(o['mode'])}</span><span>{e(o['hours'])} hrs</span></div><div class="skills"><strong>Skills:</strong> {e(o['skills'])}</div><div class="bar"><i style="width:{score}%"></i></div><div class="why">{e(why)}</div><div class="card-bottom">{action}</div></article>'''

def dashboard(c,u,token):
    if u['role']=='youth':
        opps=c.execute('SELECT o.*,u.name org FROM opportunities o JOIN users u ON u.id=o.ngo_id ORDER BY o.id').fetchall()
        apps=c.execute('SELECT a.*,o.hours FROM applications a JOIN opportunities o ON o.id=a.opportunity_id WHERE youth_id=?',(u['id'],)).fetchall()
        applied={a['opportunity_id']:a['status'] for a in apps}; complete=[a for a in apps if a['status']=='Completed']
        cards=''.join(opportunity_card(o,s,w,applied,token) for o,s,w,_ in recommend(u,opps)) or empty('No opportunities yet.')
        if not u['skills'] and not u['interests']: cards=empty('Complete your profile to receive meaningful recommendations.')+cards
        return f'''<div class="heading"><div><span class="eyebrow">YOUTH DASHBOARD</span><h1>Welcome, {e(u['name'])}.</h1><p>Discover opportunities tailored to your profile.</p></div><a class="btn outline" href="/profile">Edit profile →</a></div><div class="stats"><div class="panel"><span>Opportunities</span><strong>{len(opps)}</strong></div><div class="panel"><span>My applications</span><strong>{len(apps)}</strong></div><div class="panel"><span>Completed</span><strong>{len(complete)}</strong></div><div class="panel"><span>Completed hours</span><strong>{sum(a['hours'] for a in complete)}</strong></div></div><div class="section-head inline"><div><h2>Recommended for you</h2><p>Ranked by TF-IDF cosine similarity, location and availability. Scores are relevance, not success probabilities.</p></div></div><div class="cards">{cards}</div>'''
    opps=c.execute('SELECT o.*,COUNT(a.id) num FROM opportunities o LEFT JOIN applications a ON a.opportunity_id=o.id WHERE ngo_id=? GROUP BY o.id ORDER BY o.id DESC',(u['id'],)).fetchall()
    apps=c.execute('SELECT a.status FROM applications a JOIN opportunities o ON o.id=a.opportunity_id WHERE o.ngo_id=?',(u['id'],)).fetchall()
    cards=''.join(f'<article class="panel opportunity"><span class="category">{e(o["category"])}</span><h3>{e(o["title"])}</h3><p>{e(o["description"])}</p><div class="chips"><span>{e(o["location"])}</span><span>{e(o["availability"])}</span><span>{o["num"]} applicants</span></div><a class="textlink" href="/applications">Review applications →</a></article>' for o in opps) or empty('Post your first opportunity.')
    return f'''<div class="heading"><div><span class="eyebrow">ORGANIZATION DASHBOARD</span><h1>Welcome, {e(u['name'])}.</h1><p>Publish projects and connect with motivated volunteers.</p></div><a class="btn" href="/post">+ Post opportunity</a></div><div class="stats"><div class="panel"><span>Published</span><strong>{len(opps)}</strong></div><div class="panel"><span>Applications</span><strong>{len(apps)}</strong></div><div class="panel"><span>Pending</span><strong>{sum(a['status']=='Pending' for a in apps)}</strong></div><div class="panel"><span>Completed</span><strong>{sum(a['status']=='Completed' for a in apps)}</strong></div></div><h2>Your opportunities</h2><div class="cards">{cards}</div>'''

class Handler(BaseHTTPRequestHandler):
    def cookies(self):
        jar=SimpleCookie()
        try: jar.load(self.headers.get('Cookie',''))
        except Exception: pass
        return jar
    def get_cookie(self,name):
        v=self.cookies().get(name); return v.value if v else ''
    def token(self):
        v=self.get_cookie('csrf'); return v if re.fullmatch(r'[a-f0-9]{64}',v) else secrets.token_hex(32)
    def current(self,c):
        import time
        return c.execute('SELECT u.* FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.token=? AND s.expires>?',(self.get_cookie('session'),int(time.time()))).fetchone()
    def send_html(self,body,token,status=200):
        data=body.encode(); self.send_response(status); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(data))); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Set-Cookie',f'csrf={token}; Path=/; HttpOnly; SameSite=Strict{COOKIE_SECURE}'); self.end_headers(); self.wfile.write(data)
    def redirect(self,path,msg='',session=None,logout=False,error=False):
        if msg: path+=('?' if '?' not in path else '&')+urlencode({'msg':msg,'error':int(error)})
        self.send_response(303); self.send_header('Location',path)
        if session: self.send_header('Set-Cookie',f'session={session}; Path=/; HttpOnly; SameSite=Strict; Max-Age=86400{COOKIE_SECURE}')
        if logout: self.send_header('Set-Cookie',f'session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0{COOKIE_SECURE}')
        self.end_headers()
    def do_GET(self):
        p=urlsplit(self.path); path=p.path; q=parse_qs(p.query); token=self.token(); msg=q.get('msg',[''])[0]; err=q.get('error',['0'])[0]=='1'
        if path=='/static/style.css':
            data=(ROOT/'static/style.css').read_bytes(); self.send_response(200); self.send_header('Content-Type','text/css; charset=utf-8'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data); return
        with database() as c:
            u=self.current(c)
            if path=='/': body=hero(); title='Home'
            elif path in ('/login','/register'):
                if u: return self.redirect('/dashboard')
                title='Sign in' if path=='/login' else 'Create account'
                fields=(field('Full name / organization name','name')+select('Account type','role',['youth','ngo']) if path=='/register' else '')+field('Email','email',typ='email')+field('Password','password',typ='password')+button(title)
                demo='<div class="demo"><strong>Try the demo</strong><p>Youth: youth@yaar.demo<br>NGO: ngo@yaar.demo<br>Password for both: Demo@123</p><small>Fictional accounts for classroom use.</small></div>' if path=='/login' else '<p class="muted">Use fictional information for the academic demo. Password: at least 8 characters.</p>'
                body=f'<section class="auth panel"><span class="eyebrow">WELCOME TO Y.A.A.R.</span><h1>{title}</h1>{demo}{form(path,fields,token)}<p class="muted">'+('<a href="/register">Create an account</a>' if path=='/login' else '<a href="/login">Already registered? Sign in</a>')+'</p></section>'
            elif not u: return self.redirect('/login','Please sign in first.')
            elif path=='/dashboard': title='Dashboard'; body=dashboard(c,u,token)
            elif path=='/profile' and u['role']=='youth':
                title='My profile'; fields=field('Name','name',u['name'])+field('Skills (comma separated)','skills',u['skills'],placeholder='teaching, coding, design')+field('Interests','interests',u['interests'],placeholder='education, environment')+field('City','location',u['location'],required=False)+select('Availability','availability',['Flexible','Weekend','Weekday'],u['availability'])+button('Save profile')
                body=f'<section class="formpanel panel"><span class="eyebrow">PERSONALIZE YOUR MATCH</span><h1>My profile</h1><p>Update your skills and preferences to refresh recommendations.</p>{form(path,fields,token)}</section>'
            elif path=='/post' and u['role']=='ngo':
                title='Post opportunity'; fields=field('Opportunity title','title')+select('Category','category',['Education','Technology','Environment','Creative','Community','Skills','Other'])+field('Required skills','skills',placeholder='teaching, communication')+text_area('Description','description',placeholder='Describe the activity and responsibilities')+field('Location','location',placeholder='Noida or Remote')+select('Availability','availability',['Flexible','Weekend','Weekday'])+select('Mode','mode',['On-site','Remote'])+field('Expected hours','hours','2',typ='number')+button('Publish opportunity')
                body=f'<section class="formpanel panel"><span class="eyebrow">ORGANIZATION TOOLS</span><h1>Post an opportunity</h1><p>Use fictional project details for this prototype.</p>{form(path,fields,token)}</section>'
            elif path=='/applications':
                title='Applications'; rows=[]
                if u['role']=='youth':
                    data=c.execute('SELECT a.*,o.title,o.hours,u.name org FROM applications a JOIN opportunities o ON o.id=a.opportunity_id JOIN users u ON u.id=o.ngo_id WHERE youth_id=? ORDER BY a.id DESC',(u['id'],)).fetchall()
                    for a in data: rows.append(f'<tr><td>{e(a["title"])}</td><td>{e(a["org"])}</td><td>{a["hours"]}</td><td>{badge(a["status"])}</td></tr>')
                    cols=['Opportunity','Organization','Hours','Status']
                else:
                    data=c.execute('SELECT a.*,o.title,u.name,u.skills FROM applications a JOIN opportunities o ON o.id=a.opportunity_id JOIN users u ON u.id=a.youth_id WHERE o.ngo_id=? ORDER BY a.id DESC',(u['id'],)).fetchall()
                    for a in data:
                        states={'Pending':['Accepted','Rejected'],'Accepted':['Completed'],'Rejected':[],'Completed':[]}[a['status']]
                        action=form('/status',hidden('application_id',a['id'])+f'<select name="status">{options(states)}</select>'+button('Update','small'),token) if states else '—'
                        rows.append(f'<tr><td>{e(a["name"])}</td><td>{e(a["title"])}</td><td>{e(a["skills"])}</td><td>{badge(a["status"])}</td><td>{action}</td></tr>')
                    cols=['Applicant','Opportunity','Skills','Status','Action']
                table='<div class="table-wrap panel"><table><thead><tr>'+''.join(f'<th>{x}</th>' for x in cols)+'</tr></thead><tbody>'+''.join(rows)+'</tbody></table></div>' if rows else empty('No applications yet.')
                body=f'<div class="heading"><div><span class="eyebrow">APPLICATION TRACKER</span><h1>{"My applications" if u["role"]=="youth" else "Review applicants"}</h1><p>Track progress from application to completion.</p></div><a class="btn outline" href="/dashboard">Back to dashboard</a></div>{table}'
            else: return self.send_html(page('Not found',empty('Page not found or not available for this account.'),u,token=token),token,404)
            self.send_html(page(title,body,u,msg,err,token),token)
    def do_POST(self):
        path=urlsplit(self.path).path
        try: size=int(self.headers.get('Content-Length','0'))
        except ValueError: size=0
        if not 0<size<=20000: return self.send_error(400,'Invalid request size')
        data=parse_qs(self.rfile.read(size).decode('utf-8','replace'),keep_blank_values=True)
        def val(key): return data.get(key,[''])[0].strip()
        csrf=self.get_cookie('csrf')
        if not csrf or not hmac.compare_digest(val('csrf'),csrf): return self.send_error(403,'Invalid form token. Reload the page.')
        with database() as c:
            u=self.current(c)
            if path=='/register':
                name,email,pw,role=val('name'),val('email').lower(),val('password'),val('role')
                if not name or len(name)>180 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email) or len(email)>180 or not 8<=len(pw)<=180 or role not in ('youth','ngo'): return self.redirect('/register','Check your name, email and password (8+ characters).',error=True)
                try: c.execute('INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)',(name,email,password_hash(pw),role))
                except sqlite3.IntegrityError: return self.redirect('/register','Email already registered.',error=True)
                return self.redirect('/login','Account created. Sign in to continue.')
            if path=='/login':
                account=c.execute('SELECT * FROM users WHERE email=?',(val('email').lower(),)).fetchone(); pw=val('password')
                if not account or len(pw)>180 or not verify(pw,account['password']): return self.redirect('/login','Incorrect email or password.',error=True)
                import time
                session=secrets.token_urlsafe(32); c.execute('DELETE FROM sessions WHERE expires<=?',(int(time.time()),)); c.execute('INSERT INTO sessions VALUES(?,?,?)',(session,account['id'],int(time.time())+86400)); dest='/profile' if account['role']=='youth' and not account['skills'] else '/dashboard'; return self.redirect(dest,session=session)
            if not u: return self.redirect('/login','Please sign in first.',error=True)
            if path=='/logout': c.execute('DELETE FROM sessions WHERE token=?',(self.get_cookie('session'),)); return self.redirect('/',logout=True)
            if path=='/profile' and u['role']=='youth':
                fields=[val(k) for k in ('name','skills','interests','location','availability')]
                if not all(fields[:3]) or max(map(len,fields))>180 or fields[4] not in ('Flexible','Weekend','Weekday'): return self.redirect('/profile','Please enter valid profile details.',error=True)
                c.execute('UPDATE users SET name=?,skills=?,interests=?,location=?,availability=? WHERE id=?',(*fields,u['id'])); return self.redirect('/dashboard','Profile saved. Recommendations updated.')
            if path=='/post' and u['role']=='ngo':
                f=[val(k) for k in ('title','category','skills','description','location','availability','mode')]
                try: hours=int(val('hours'))
                except ValueError: hours=0
                if not all(f) or any(len(x)>180 for i,x in enumerate(f) if i!=3) or len(f[3])>1500 or not 1<=hours<=200 or f[1] not in ('Education','Technology','Environment','Creative','Community','Skills','Other') or f[5] not in ('Flexible','Weekend','Weekday') or f[6] not in ('On-site','Remote'): return self.redirect('/post','Please enter valid opportunity details and 1–200 hours.',error=True)
                c.execute('INSERT INTO opportunities(ngo_id,title,category,skills,description,location,availability,mode,hours) VALUES(?,?,?,?,?,?,?,?,?)',(u['id'],*f,hours)); return self.redirect('/dashboard','Opportunity published successfully.')
            if path=='/apply' and u['role']=='youth':
                oid=val('opportunity_id')
                if not c.execute('SELECT 1 FROM opportunities WHERE id=?',(oid,)).fetchone(): return self.redirect('/dashboard','Opportunity not found.',error=True)
                try: c.execute('INSERT INTO applications(youth_id,opportunity_id) VALUES(?,?)',(u['id'],oid))
                except sqlite3.IntegrityError: return self.redirect('/dashboard','You have already applied.',error=True)
                return self.redirect('/applications','Application submitted.')
            if path=='/status' and u['role']=='ngo':
                a=c.execute('SELECT a.* FROM applications a JOIN opportunities o ON o.id=a.opportunity_id WHERE a.id=? AND o.ngo_id=?',(val('application_id'),u['id'])).fetchone(); status=val('status')
                allowed={'Pending':('Accepted','Rejected'),'Accepted':('Completed',)}
                if not a or status not in allowed.get(a['status'],()): return self.redirect('/applications','Invalid status change.',error=True)
                c.execute('UPDATE applications SET status=? WHERE id=?',(status,a['id'])); return self.redirect('/applications','Application status updated.')
        self.send_error(403,'Action not allowed')

def main():
    init_db(); server=ThreadingHTTPServer((HOST,PORT),Handler); url=f'http://127.0.0.1:{PORT}'
    print('\nY.A.A.R. is running at '+url+'\nKeep this window open. Press Ctrl+C to stop.\n',flush=True)
    if not IS_CLOUD and '--no-browser' not in __import__('sys').argv: threading.Timer(.8,lambda:webbrowser.open(url)).start()
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
if __name__=='__main__': main()
