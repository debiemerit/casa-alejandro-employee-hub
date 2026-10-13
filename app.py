import os, io, secrets, calendar, math, uuid, csv, hashlib, json, subprocess, tempfile, zipfile, shutil, re
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from functools import wraps
from zoneinfo import ZoneInfo
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort, send_file, jsonify, Response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from PIL import Image
import pyotp
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas

app=Flask(__name__)
app.config['SECRET_KEY']=os.environ.get('SECRET_KEY') or ('dev-only-change-me' if os.environ.get('FLASK_DEBUG')=='1' else None)
if not app.config['SECRET_KEY']: raise RuntimeError('Set SECRET_KEY')
dburl=os.environ.get('DATABASE_URL','sqlite:///casa.db')
if dburl.startswith('postgres://'): dburl='postgresql://'+dburl[len('postgres://'):]
if dburl.startswith('postgresql://'): dburl=dburl.replace('postgresql://','postgresql+psycopg://',1)
app.config['SQLALCHEMY_DATABASE_URI']=dburl
app.config['SQLALCHEMY_TRACK_MODIFICATIONS']=False
app.config['MAX_CONTENT_LENGTH']=5*1024*1024
app.config.update(SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE','1')=='1')
db=SQLAlchemy(app)
TZ=ZoneInfo('Asia/Manila')
PHOTO_DIR=os.environ.get('PHOTO_STORAGE_DIR',os.path.join(app.instance_path,'uploads'))

class User(db.Model):
 id=db.Column(db.Integer,primary_key=True)
 username=db.Column(db.String(80),unique=True,nullable=False)
 name=db.Column(db.String(160),nullable=False)
 password_hash=db.Column(db.String(256),nullable=False)
 role=db.Column(db.String(20),nullable=False,default='employee')
 position=db.Column(db.String(100),default='Staff')
 daily_rate=db.Column(db.Numeric(12,2),default=0)
 active=db.Column(db.Boolean,default=True)
 created_at=db.Column(db.DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
 rest_weekday=db.Column(db.Integer,default=6)
 otp_secret=db.Column(db.String(64),nullable=True)

class Shift(db.Model):
 id=db.Column(db.Integer,primary_key=True)
 user_id=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False)
 start_at=db.Column(db.DateTime(timezone=True),nullable=False)
 end_at=db.Column(db.DateTime(timezone=True),nullable=False)
 note=db.Column(db.String(200),default='')
 published=db.Column(db.Boolean,default=True)

class Attendance(db.Model):
 id=db.Column(db.Integer,primary_key=True)
 user_id=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False)
 kind=db.Column(db.String(12),nullable=False)
 at=db.Column(db.DateTime(timezone=True),default=lambda:datetime.now(timezone.utc),nullable=False)
 lat=db.Column(db.Float,nullable=False)
 lng=db.Column(db.Float,nullable=False)
 accuracy=db.Column(db.Float,nullable=False)
 photo=db.Column(db.String(120),nullable=False)
 status=db.Column(db.String(20),default='pending')
 reviewer_id=db.Column(db.Integer,db.ForeignKey('user.id'))
 reviewed_at=db.Column(db.DateTime(timezone=True))
 note=db.Column(db.String(300),default='')
 outside_geofence=db.Column(db.Boolean,default=False)

class Holiday(db.Model):
 id=db.Column(db.Integer,primary_key=True)
 day=db.Column(db.Date,unique=True,nullable=False)
 name=db.Column(db.String(140),nullable=False)
 category=db.Column(db.String(30),nullable=False)

class Setting(db.Model):
 key=db.Column(db.String(80),primary_key=True)
 value=db.Column(db.String(250),nullable=False)

class Payroll(db.Model):
 id=db.Column(db.Integer,primary_key=True)
 user_id=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False)
 start_day=db.Column(db.Date,nullable=False)
 end_day=db.Column(db.Date,nullable=False)
 basic=db.Column(db.Numeric(12,2),default=0)
 premiums=db.Column(db.Numeric(12,2),default=0)
 overtime=db.Column(db.Numeric(12,2),default=0)
 night=db.Column(db.Numeric(12,2),default=0)
 allowance=db.Column(db.Numeric(12,2),default=0)
 sss=db.Column(db.Numeric(12,2),default=0)
 philhealth=db.Column(db.Numeric(12,2),default=0)
 pagibig=db.Column(db.Numeric(12,2),default=0)
 tax=db.Column(db.Numeric(12,2),default=0)
 other=db.Column(db.Numeric(12,2),default=0)
 thirteenth_base=db.Column(db.Numeric(12,2),default=0)
 status=db.Column(db.String(20),default='draft')
 approved_at=db.Column(db.DateTime(timezone=True))
 __table_args__=(UniqueConstraint('user_id','start_day','end_day',name='one_payroll_period'),)

class PushSubscription(db.Model):
 id=db.Column(db.Integer,primary_key=True)
 user_id=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False)
 endpoint=db.Column(db.Text,unique=True,nullable=False)
 p256dh=db.Column(db.Text,nullable=False)
 auth=db.Column(db.Text,nullable=False)

class LeaveRequest(db.Model):
 id=db.Column(db.Integer,primary_key=True)
 user_id=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False)
 start_day=db.Column(db.Date,nullable=False)
 end_day=db.Column(db.Date,nullable=False)
 kind=db.Column(db.String(30),nullable=False)
 reason=db.Column(db.String(500),default='')
 status=db.Column(db.String(20),default='pending')
 reviewer_id=db.Column(db.Integer)

class Availability(db.Model):
 id=db.Column(db.Integer,primary_key=True)
 user_id=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False)
 day=db.Column(db.Date,nullable=False)
 available=db.Column(db.Boolean,default=False)
 note=db.Column(db.String(300),default='')
 __table_args__=(UniqueConstraint('user_id','day',name='availability_one_day'),)

class SwapRequest(db.Model):
 id=db.Column(db.Integer,primary_key=True)
 shift_id=db.Column(db.Integer,db.ForeignKey('shift.id'),nullable=False)
 user_id=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False)
 target_id=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False)
 status=db.Column(db.String(20),default='pending')

class BreakRecord(db.Model):
 id=db.Column(db.Integer,primary_key=True)
 user_id=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False)
 kind=db.Column(db.String(10),nullable=False)
 at=db.Column(db.DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))

class PayrollRule(db.Model):
 id=db.Column(db.Integer,primary_key=True)
 agency=db.Column(db.String(20),nullable=False)
 min_comp=db.Column(db.Numeric(12,2),nullable=False)
 max_comp=db.Column(db.Numeric(12,2),nullable=False)
 employee_amount=db.Column(db.Numeric(12,2),nullable=False)
 effective_from=db.Column(db.Date,nullable=False)
 __table_args__=(UniqueConstraint('agency','min_comp','max_comp','effective_from',name='rule_unique'),)

class Notice(db.Model):
 id=db.Column(db.Integer,primary_key=True)
 user_id=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False)
 message=db.Column(db.String(250),nullable=False)
 created_at=db.Column(db.DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))

class Audit(db.Model):
 id=db.Column(db.Integer,primary_key=True)
 actor_id=db.Column(db.Integer)
 action=db.Column(db.String(120),nullable=False)
 details=db.Column(db.String(500),default='')
 at=db.Column(db.DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))

def log(action,details=''):
 db.session.add(Audit(actor_id=session.get('uid'),action=action,details=str(details)[:500]))
def now():return datetime.now(timezone.utc)
def local(dt):
 if not dt:return None
 return (dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt).astimezone(TZ)
def phpdate(d):return d.strftime('%Y-%m-%d')
def money(v):return f'{Decimal(str(v or 0)):,.2f}'
def decimal(v):return Decimal(str(v or '0')).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
def user():return db.session.get(User,session['uid']) if session.get('uid') else None
@app.context_processor
def context():return dict(me=user(),local=local,money=money,csrf=session.get('csrf',''))
@app.before_request
def csrf_protect():
 if 'csrf' not in session:session['csrf']=secrets.token_urlsafe(32)
 if request.method in ('POST','PUT','PATCH','DELETE'):
  if not secrets.compare_digest(request.form.get('csrf',request.headers.get('X-CSRF-Token','')),session['csrf']):abort(400,'Invalid CSRF token')

def login_required(fn):
 @wraps(fn)
 def inner(*args,**kwargs):
  if not user():return redirect(url_for('login'))
  if not user().active:session.clear();return redirect(url_for('login'))
  return fn(*args,**kwargs)
 return inner
def manager_required(fn):
 @wraps(fn)
 @login_required
 def inner(*args,**kwargs):
  if user().role not in ('manager','admin'):abort(403)
  return fn(*args,**kwargs)
 return inner
def admin_required(fn):
 @wraps(fn)
 @login_required
 def inner(*args,**kwargs):
  if user().role!='admin':abort(403)
  return fn(*args,**kwargs)
 return inner

def get_setting(k,default):
 s=db.session.get(Setting,k);return s.value if s else str(default)
def multiplier(kind):
 defaults={'ordinary':'1','rest':'1.3','regular':'2','regular_rest':'2.6','special':'1.3','special_rest':'1.5','special_working':'1'}
 return decimal(get_setting('mult_'+kind,defaults.get(kind,'1')))
def holiday_kind(day,rest=False):
 h=Holiday.query.filter_by(day=day).first()
 category=h.category if h else 'ordinary'
 if rest and category=='regular':return 'regular_rest'
 if rest and category=='special':return 'special_rest'
 if rest and category=='ordinary':return 'rest'
 return category

@app.route('/healthz')
def health():return {'ok':True}
@app.route('/login',methods=['GET','POST'])
def login():
 if request.method=='POST':
  u=User.query.filter_by(username=request.form.get('username','').strip()).first()
  if not u or not u.active or not check_password_hash(u.password_hash,request.form.get('password','')):
   flash('Invalid login','error');return render_template('login.html'),401
  session.clear();session['csrf']=secrets.token_urlsafe(32)
  session['pending_uid']=u.id
  return redirect(url_for('otp_verify'))
 return render_template('login.html')
@app.post('/logout')
@login_required
def logout():session.clear();return redirect(url_for('login'))

@app.route('/otp/verify',methods=['GET','POST'])
def otp_verify():
 uid=session.get('pending_uid')
 if not uid:return redirect(url_for('login'))
 u=db.session.get(User,uid)
 if not u or not u.active:session.clear();return redirect(url_for('login'))
 if request.method=='POST':
  code=request.form.get('code','').strip().replace(' ','')
  if not u.otp_secret:return redirect(url_for('otp_enroll'))
  if not pyotp.TOTP(u.otp_secret).verify(code,valid_window=1):
   flash('Invalid authenticator code','error');return render_template('otp_verify.html',setup=not bool(u.otp_secret),secret=u.otp_secret),401
  session.pop('pending_uid',None);session['uid']=u.id
  session['csrf']=secrets.token_urlsafe(32)
  audit('login_otp',str(u.id));db.session.commit()
  return redirect(url_for('home'))
 return redirect(url_for('otp_enroll')) if not u.otp_secret else render_template('otp_verify.html',setup=False,secret=None)

@app.route('/otp/enroll',methods=['GET','POST'])
def otp_enroll():
 uid=session.get('pending_uid')
 if not uid:return redirect(url_for('login'))
 u=db.session.get(User,uid)
 if not u or not u.active:return redirect(url_for('login'))
 if u.otp_secret:return redirect(url_for('otp_verify'))
 u.otp_secret=pyotp.random_base32();db.session.commit()
 if request.method=='POST':return redirect(url_for('otp_verify'))
 return render_template('otp_enroll.html',secret=u.otp_secret,uri=pyotp.TOTP(u.otp_secret).provisioning_uri(name=u.username,issuer_name='Casa Alejandro'))

@app.route('/admin/data')
@admin_required
def admin_data():return render_template('admin_data.html')

@app.get('/admin/export/<dataset>.csv')
@admin_required
def admin_export(dataset):
 definitions={
  'employees':(User,['id','username','name','role','position','daily_rate','active','rest_weekday']),
  'shifts':(Shift,['id','user_id','start_at','end_at','note','published']),
  'attendance':(Attendance,['id','user_id','kind','at','lat','lng','accuracy','status','outside_geofence']),
  'holidays':(Holiday,['id','day','name','category']),
  'payroll':(Payroll,[c.name for c in Payroll.__table__.columns]),
 }
 if dataset not in definitions:abort(404)
 model,columns=definitions[dataset]
 buf=io.StringIO();writer=csv.writer(buf);writer.writerow(columns)
 for record in model.query.order_by(model.id).all():writer.writerow([getattr(record,k) for k in columns])
 audit('csv_export',dataset);db.session.commit()
 return Response(buf.getvalue(),mimetype='text/csv',headers={'Content-Disposition':f'attachment; filename="casa_{dataset}.csv"','Cache-Control':'no-store'})

@app.post('/admin/import/employees')
@admin_required
def admin_import_employees():
 upload=request.files.get('file')
 if not upload or not upload.filename.lower().endswith('.csv'):abort(400,'Upload a CSV file')
 try:
  raw=upload.read().decode('utf-8-sig');rows=list(csv.DictReader(io.StringIO(raw)))
  if len(rows)>1000:abort(400,'Maximum 1000 rows')
  required={'username','name','position','daily_rate'}
  if not rows or not required.issubset(rows[0]):abort(400,'Missing required CSV columns')
  created=0;updated=0
  for r in rows:
   username=r['username'].strip();name=r['name'].strip()
   if not re.fullmatch(r'[A-Za-z0-9_.-]{3,80}',username) or not name:raise ValueError('Invalid employee username/name')
   amount=decimal(r['daily_rate'])
   if amount<0:raise ValueError('Invalid daily rate')
   u=User.query.filter_by(username=username).first()
   if u:
    if u.role=='admin':raise ValueError('Admin accounts cannot be changed by CSV')
    u.name=name;u.position=r['position'][:100];u.daily_rate=amount;updated+=1
   else:
    pwd=secrets.token_urlsafe(24)
    db.session.add(User(username=username,name=name,position=r['position'][:100],daily_rate=amount,role='employee',password_hash=generate_password_hash(pwd),active=False));created+=1
  audit('employees_import',f'created={created}, updated={updated}');db.session.commit()
  flash(f'Imported {created} new disabled accounts and updated {updated}. Set passwords and activate new accounts individually.','success')
 except Exception as e:
  db.session.rollback();flash('Import failed: '+str(e)[:160],'error')
 return redirect(url_for('admin_data'))

@app.get('/admin/backup')
@admin_required
def admin_backup():
 if not app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgresql'):abort(400,'PostgreSQL required for full backup')
 # pg_dump credentials inherited only in subprocess environment; never place credentials in command arguments.
 dburl=os.environ.get('DATABASE_URL','')
 if not dburl:abort(503,'DATABASE_URL missing')
 with tempfile.TemporaryDirectory() as tmp:
  dump=os.path.join(tmp,'database.dump')
  try:
   subprocess.run(['pg_dump','--format=custom','--file',dump,dburl],check=True,timeout=120,capture_output=True)
  except (OSError,subprocess.SubprocessError):abort(503,'Backup unavailable. Install PostgreSQL client tools and verify database connectivity.')
  out=io.BytesIO()
  with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED) as z:
   z.write(dump,'database.dump')
   z.writestr('README.txt','Encrypted offsite storage required. Restore with pg_restore in maintenance mode. Contains confidential employee data.\n')
   if os.path.isdir(PHOTO_DIR):
    for root,dirs,files in os.walk(PHOTO_DIR):
     for name in files:
      path=os.path.join(root,name)
      if os.path.islink(path):continue
      z.write(path,'photos/'+os.path.relpath(path,PHOTO_DIR))
  out.seek(0)
  audit('full_backup_download','database + photos');db.session.commit()
  return send_file(out,mimetype='application/zip',as_attachment=True,download_name='casa_backup_'+now().strftime('%Y%m%d_%H%M')+'.zip')

@app.route('/')
@login_required
def home():
 shifts=Shift.query.filter_by(user_id=user().id,published=True).filter(Shift.end_at>=now()).order_by(Shift.start_at).limit(12).all()
 attendance=Attendance.query.filter_by(user_id=user().id).order_by(Attendance.at.desc()).limit(12).all()
 payrolls=Payroll.query.filter_by(user_id=user().id,status='approved').order_by(Payroll.end_day.desc()).limit(5).all()
 notices=Notice.query.filter_by(user_id=user().id).order_by(Notice.created_at.desc()).limit(5).all()
 return render_template('home.html',shifts=shifts,attendance=attendance,payrolls=payrolls,notices=notices)
@app.post('/punch')
@login_required
def punch():
 kind=request.form.get('kind')
 if kind not in ('in','out'):abort(400)
 last=Attendance.query.filter_by(user_id=user().id).order_by(Attendance.at.desc()).first()
 if last and last.kind==kind:flash('Clock '+kind+' already recorded. Contact your manager to correct it.','error');return redirect(url_for('home'))
 try:
  lat=float(request.form['lat']);lng=float(request.form['lng']);accuracy=float(request.form['accuracy'])
  if not (-90<=lat<=90 and -180<=lng<=180 and 0<=accuracy<=5000):raise ValueError()
 except (ValueError,KeyError):abort(400,'GPS location required')
 photo=request.files.get('photo')
 if not photo:abort(400,'Selfie required')
 maxbytes=int(os.getenv('MAX_PHOTO_BYTES','3000000'))
 raw=photo.read(maxbytes+1)
 if len(raw)>maxbytes:abort(400,'Photo too large')
 try:
  img=Image.open(io.BytesIO(raw));img.verify()
  img=Image.open(io.BytesIO(raw)).convert('RGB')
  if img.width*img.height>16000000:abort(400,'Image too large')
  img.thumbnail((1200,1200))
 except Exception:abort(400,'Invalid image')
 os.makedirs(PHOTO_DIR,exist_ok=True)
 filename=uuid.uuid4().hex+'.jpg'
 img.save(os.path.join(PHOTO_DIR,filename),'JPEG',quality=78)
 radius=float(get_setting('geofence_radius','100'))
 centre_lat=get_setting('geofence_lat','');centre_lng=get_setting('geofence_lng','')
 outside=False
 if centre_lat and centre_lng:
  from math import radians,sin,cos,asin,sqrt
  a1=radians(float(centre_lat));a2=radians(lat);dlat=a2-a1;dlng=radians(lng-float(centre_lng))
  metres=6371000*2*asin(min(1,sqrt(sin(dlat/2)**2+cos(a1)*cos(a2)*sin(dlng/2)**2)))
  outside=metres>radius or accuracy>float(get_setting('gps_max_accuracy','150'))
  if outside and get_setting('geofence_policy','review')=='block':abort(400,'Outside restaurant geofence; contact your manager')
 a=Attendance(user_id=user().id,kind=kind,lat=lat,lng=lng,accuracy=accuracy,photo=filename,outside_geofence=outside)
 db.session.add(a);log('attendance',kind);db.session.commit()
 flash('Attendance submitted for manager review.','success');return redirect(url_for('home'))
@app.get('/photo/<int:attendance_id>')
@login_required
def photo(attendance_id):
 a=db.get_or_404(Attendance,attendance_id)
 if user().role not in ('manager','admin') and a.user_id!=user().id:abort(403)
 path=os.path.join(PHOTO_DIR,os.path.basename(a.photo))
 if not os.path.isfile(path):abort(404)
 return send_file(path,mimetype='image/jpeg',max_age=0)
@app.get('/timesheets')
@login_required
def timesheets():
 uid=request.args.get('user_id',type=int) if user().role in ('manager','admin') else user().id
 q=Attendance.query
 if uid:q=q.filter_by(user_id=uid)
 rows=q.order_by(Attendance.at.desc()).limit(300).all()
 return render_template('timesheets.html',rows=rows,employees=User.query.order_by(User.name).all() if user().role in ('manager','admin') else [],selected=uid)
@app.post('/attendance/<int:aid>/review')
@manager_required
def review(aid):
 a=db.get_or_404(Attendance,aid)
 if request.form.get('status') not in ('approved','rejected'):abort(400)
 a.status=request.form['status'];a.reviewer_id=user().id;a.reviewed_at=now();a.note=request.form.get('note','')[:300]
 log('attendance_review',f'{aid} {a.status}');db.session.commit();return redirect(url_for('timesheets'))
@app.get('/roster')
@login_required
def roster():
 q=Shift.query
 if user().role=='employee':q=q.filter_by(user_id=user().id,published=True)
 shifts=q.filter(Shift.end_at>=now()-timedelta(days=30)).order_by(Shift.start_at).limit(200).all()
 return render_template('roster.html',shifts=shifts,employees=User.query.filter_by(active=True).order_by(User.name).all() if user().role!='employee' else [])
@app.post('/roster')
@manager_required
def roster_add():
 u=db.get_or_404(User,int(request.form['user_id']))
 try:
  start=datetime.fromisoformat(request.form['start']).replace(tzinfo=TZ).astimezone(timezone.utc)
  end=datetime.fromisoformat(request.form['end']).replace(tzinfo=TZ).astimezone(timezone.utc)
 except ValueError:abort(400,'Invalid dates')
 if end<=start or end-start>timedelta(hours=24):abort(400,'Invalid shift length')
 s=Shift(user_id=u.id,start_at=start,end_at=end,note=request.form.get('note','')[:200]);db.session.add(s)
 db.session.add(Notice(user_id=u.id,message='New shift: '+local(start).strftime('%b %d, %I:%M %p')))
 notify_push(u.id,'New shift','Check your Casa Alejandro roster')
 log('shift_created',u.username);db.session.commit();flash('Shift published','success');return redirect(url_for('roster'))
@app.post('/roster/<int:sid>/delete')
@manager_required
def roster_delete(sid):
 s=db.get_or_404(Shift,sid)
 db.session.add(Notice(user_id=s.user_id,message='A scheduled shift was cancelled. Check your roster.'))
 notify_push(s.user_id,'Shift cancelled','Check your updated roster')
 db.session.delete(s);log('shift_cancelled',sid);db.session.commit();return redirect(url_for('roster'))
@app.route('/employees',methods=['GET','POST'])
@admin_required
def employees():
 if request.method=='POST':
  username=request.form.get('username','').strip().lower();password=request.form.get('password','')
  if not username or len(password)<12 or User.query.filter_by(username=username).first():flash('Username must be unique; password at least 12 characters.','error')
  else:
   u=User(username=username,name=request.form['name'][:160],password_hash=generate_password_hash(password),role=request.form.get('role','employee') if request.form.get('role') in ('employee','manager','admin') else 'employee',position=request.form.get('position','Staff')[:100],daily_rate=decimal(request.form.get('daily_rate','0')),rest_weekday=int(request.form.get('rest_weekday','6')))
   db.session.add(u);log('employee_created',username);db.session.commit();flash('Employee created','success')
 return render_template('employees.html',employees=User.query.order_by(User.name).all())
@app.post('/employees/<int:uid>/password')
@admin_required
def reset_password(uid):
 u=db.get_or_404(User,uid);password=request.form.get('password','')
 if len(password)<12:abort(400,'Password minimum 12 characters')
 u.password_hash=generate_password_hash(password);log('password_reset',u.username);db.session.commit();flash('Password updated','success');return redirect(url_for('employees'))
@app.post('/employees/<int:uid>/status')
@admin_required
def toggle_employee(uid):
 u=db.get_or_404(User,uid)
 if u.id==user().id:abort(400,'Cannot deactivate yourself')
 u.active=not u.active;log('employee_status',f'{u.username} {u.active}');db.session.commit();return redirect(url_for('employees'))
@app.route('/holidays',methods=['GET','POST'])
@manager_required
def holidays():
 if request.method=='POST':
  day=date.fromisoformat(request.form['day']);category=request.form['category']
  if category not in ('regular','special','special_working'):abort(400)
  h=Holiday.query.filter_by(day=day).first()
  if not h:h=Holiday(day=day);db.session.add(h)
  h.name=request.form['name'][:140];h.category=category
  log('holiday_saved',day);db.session.commit()
 return render_template('holidays.html',holidays=Holiday.query.order_by(Holiday.day).all(),multipliers={k:multiplier(k) for k in ['ordinary','rest','regular','regular_rest','special','special_rest','special_working']})
@app.post('/multipliers')
@admin_required
def multipliers():
 for k in ['ordinary','rest','regular','regular_rest','special','special_rest','special_working']:
  v=decimal(request.form.get(k,'0'))
  if v<0 or v>10:abort(400)
  db.session.merge(Setting(key='mult_'+k,value=str(v)))
 log('pay_multipliers_changed');db.session.commit();return redirect(url_for('holidays'))

def period_from_string(v):
 year,month,half=[int(x) for x in v.split('-')]
 if year<2020 or year>2100 or month not in range(1,13) or half not in (1,2):raise ValueError()
 return (date(year,month,1 if half==1 else 16),date(year,month,15 if half==1 else calendar.monthrange(year,month)[1]))

def approved_hours(uid,start,end):
 rows=Attendance.query.filter_by(user_id=uid,status='approved').order_by(Attendance.at).all()
 total=Decimal('0');punch=None;daily={}
 for a in rows:
  if a.kind=='in':punch=a
  elif a.kind=='out' and punch:
   start_dt=punch.at.replace(tzinfo=timezone.utc) if punch.at.tzinfo is None else punch.at
   end_dt=a.at.replace(tzinfo=timezone.utc) if a.at.tzinfo is None else a.at
   day=local(start_dt).date()
   if start<=day<=end and end_dt>start_dt and end_dt-start_dt<=timedelta(hours=24):
    hours=Decimal(str((end_dt-start_dt).total_seconds()/3600));daily[day]=daily.get(day,Decimal('0'))+hours
   punch=None
 return daily

@app.route('/payroll',methods=['GET','POST'])
@manager_required
def payroll():
 if request.method=='POST':
  try:start,end=period_from_string(request.form['period'])
  except Exception:abort(400,'Invalid period')
  uid=int(request.form['user_id']);u=db.get_or_404(User,uid)
  if Payroll.query.filter_by(user_id=uid,start_day=start,end_day=end).first():flash('Payroll already exists for this period','error');return redirect(url_for('payroll'))
  daily=approved_hours(uid,start,end);basic=Decimal('0');premiums=Decimal('0');overtime=Decimal('0')
  for day,hours in daily.items():
   rest=day.weekday()==(u.rest_weekday if u.rest_weekday is not None else 6)
   kind=holiday_kind(day,rest)
   regular=min(max(hours-Decimal(str(break_hours(uid,day))),Decimal('0')),Decimal('8'))
   daily_base=decimal(u.daily_rate or 0)
   base=regular/Decimal('8')*daily_base
   basic+=base
   premiums+=base*(multiplier(kind)-Decimal('1'))
   if hours-Decimal(str(break_hours(uid,day)))>8:
    # OT factor = applicable first-eight-hours multiplier * 1.30 (holiday/rest), ordinary 1.25
    factor=multiplier(kind)*(Decimal('1.25') if kind in ('ordinary','special_working') else Decimal('1.30'))
    overtime+=(hours-Decimal(str(break_hours(uid,day)))-8)/Decimal('8')*daily_base*factor
  p=Payroll(user_id=uid,start_day=start,end_day=end,basic=decimal(basic),premiums=decimal(premiums),overtime=decimal(overtime),thirteenth_base=decimal(basic))
  # Statutory deductions remain zero until verified by payroll staff.
  # Contribution bracket reference entries are NOT applied automatically because
  # Philippine contributions can depend on monthly bases and other components.
  db.session.add(p);log('payroll_draft',f'{uid} {start}');db.session.commit();flash('Draft created; verify rest days, breaks, holidays, night hours and statutory deductions.','success');return redirect(url_for('payroll_edit',pid=p.id))
 rows=Payroll.query.order_by(Payroll.start_day.desc()).limit(100).all()
 return render_template('payroll.html',rows=rows,employees=User.query.filter_by(active=True).all())
@app.route('/payroll/<int:pid>',methods=['GET','POST'])
@manager_required
def payroll_edit(pid):
 p=db.get_or_404(Payroll,pid)
 if request.method=='POST':
  if p.status!='draft':abort(400,'Approved payroll is locked')
  for field in ['basic','premiums','overtime','night','allowance','sss','philhealth','pagibig','tax','other','thirteenth_base']:
   v=decimal(request.form.get(field,'0'))
   if v<0:abort(400,'Negative amounts not allowed')
   setattr(p,field,v)
  log('payroll_edited',pid);db.session.commit();flash('Draft saved','success')
 return render_template('payroll_edit.html',p=p,employee=db.session.get(User,p.user_id))
@app.post('/payroll/<int:pid>/approve')
@manager_required
def payroll_approve(pid):
 p=db.get_or_404(Payroll,pid)
 if p.status!='draft':abort(400)
 p.status='approved';p.approved_at=now();db.session.add(Notice(user_id=p.user_id,message=f'Your payslip for {p.start_day} to {p.end_day} is available.'))
 notify_push(p.user_id,'Payslip available','Open your Casa Alejandro payslips')
 log('payroll_approved',pid);db.session.commit();return redirect(url_for('payroll'))
@app.get('/payslips')
@login_required
def payslips():
 q=Payroll.query.filter_by(status='approved')
 if user().role=='employee':q=q.filter_by(user_id=user().id)
 return render_template('payslips.html',rows=q.order_by(Payroll.end_day.desc()).limit(150).all())
@app.get('/payslip/<int:pid>.pdf')
@login_required
def payslip_pdf(pid):
 p=db.get_or_404(Payroll,pid)
 if p.status!='approved':abort(403)
 if user().role=='employee' and p.user_id!=user().id:abort(403)
 employee=db.session.get(User,p.user_id)
 buf=io.BytesIO();c=Canvas(buf,pagesize=A4);w,h=A4
 c.setTitle('Casa Alejandro Payslip');c.setFont('Helvetica-Bold',18);c.drawString(44,h-58,'CASA ALEJANDRO')
 c.setFont('Helvetica',10);c.drawString(44,h-80,'Employee Payslip - Philippines')
 c.drawString(44,h-112,'Employee: '+employee.name);c.drawString(44,h-128,'Position: '+(employee.position or ''))
 c.drawString(44,h-144,f'Period: {p.start_day} to {p.end_day}')
 c.drawString(44,h-160,'Payroll status: APPROVED')
 y=h-195
 def line(label,value):
  nonlocal y
  c.drawString(44,y,label);c.drawRightString(w-44,y,'PHP '+money(value));y-=22
 c.setFont('Helvetica-Bold',11);c.drawString(44,y,'EARNINGS');y-=23;c.setFont('Helvetica',10)
 for label,key in [('Basic pay','basic'),('Holiday / rest premiums','premiums'),('Overtime','overtime'),('Night differential','night'),('Allowances','allowance')]:line(label,getattr(p,key))
 gross=sum(Decimal(str(getattr(p,k))) for k in ['basic','premiums','overtime','night','allowance'])
 c.setFont('Helvetica-Bold',10);line('GROSS PAY',gross)
 y-=10;c.drawString(44,y,'DEDUCTIONS');y-=23;c.setFont('Helvetica',10)
 for label,key in [('SSS','sss'),('PhilHealth','philhealth'),('Pag-IBIG','pagibig'),('Withholding tax','tax'),('Other deductions','other')]:line(label,getattr(p,key))
 deductions=sum(Decimal(str(getattr(p,k))) for k in ['sss','philhealth','pagibig','tax','other'])
 c.setFont('Helvetica-Bold',11);line('NET PAY',gross-deductions)
 y-=15;c.setFont('Helvetica',9);c.drawString(44,y,'13th-month basic salary base recorded this period: PHP '+money(p.thirteenth_base))
 y-=22;c.drawString(44,y,'Generated from approved payroll. Retain payroll supporting records.')
 c.showPage();c.save();buf.seek(0)
 return send_file(buf,mimetype='application/pdf',as_attachment=True,download_name=f'CasaAlejandro-Payslip-{pid}.pdf')
@app.get('/thirteenth')
@manager_required
def thirteenth():
 year=request.args.get('year',date.today().year,type=int)
 rows=Payroll.query.filter_by(status='approved').filter(Payroll.start_day>=date(year,1,1),Payroll.end_day<=date(year,12,31)).all()
 totals={}
 for p in rows:totals[p.user_id]=totals.get(p.user_id,Decimal('0'))+Decimal(str(p.thirteenth_base or 0))
 return render_template('thirteenth.html',year=year,totals=[(db.session.get(User,uid),decimal(total/12),total) for uid,total in totals.items()])


def notify_push(uid,title,body):
 # Optional best-effort push; errors must never block roster or payroll transactions.
 private=os.getenv('VAPID_PRIVATE_KEY');subject=os.getenv('VAPID_SUBJECT')
 if not private or not subject:return
 try:
  from pywebpush import webpush
  for sub in PushSubscription.query.filter_by(user_id=uid).all():
   try:webpush(subscription_info={'endpoint':sub.endpoint,'keys':{'p256dh':sub.p256dh,'auth':sub.auth}},data=json.dumps({'title':title,'body':body}),vapid_private_key=private,vapid_claims={'sub':subject},ttl=3600)
   except Exception:app.logger.exception('Push delivery failed')
 except Exception:app.logger.exception('Push integration failed')

@app.get('/push/public-key')
@login_required
def push_public_key():return jsonify({'publicKey':os.getenv('VAPID_PUBLIC_KEY','')})

@app.post('/push/subscribe')
@login_required
def push_subscribe():
 data=request.get_json(silent=True) or {};keys=data.get('keys') or {};endpoint=data.get('endpoint','')
 if not endpoint.startswith('https://') or len(endpoint)>2000 or not keys.get('p256dh') or not keys.get('auth'):abort(400)
 sub=PushSubscription.query.filter_by(endpoint=endpoint).first()
 if not sub:sub=PushSubscription(endpoint=endpoint);db.session.add(sub)
 sub.user_id=user().id;sub.p256dh=keys['p256dh'][:500];sub.auth=keys['auth'][:500];db.session.commit()
 return jsonify({'ok':True})

@app.get('/sw.js')
def service_worker():
 return send_file(os.path.join(app.static_folder,'sw.js'),mimetype='application/javascript')

def break_hours(uid,day):
 rows=BreakRecord.query.filter_by(user_id=uid).order_by(BreakRecord.at).all()
 start=None;total=0.0
 for r in rows:
  if r.kind=='start':start=r.at
  elif r.kind=='end' and start:
   if local(start).date()==day and r.at>start and r.at-start<timedelta(hours=8):total+=(r.at-start).total_seconds()/3600
   start=None
 return round(total,4)

@app.post('/break')
@login_required
def record_break():
 kind=request.form.get('kind')
 if kind not in ('start','end'):abort(400)
 last=BreakRecord.query.filter_by(user_id=user().id).order_by(BreakRecord.at.desc()).first()
 if kind=='end' and (not last or last.kind!='start'):abort(400,'No active break')
 if kind=='start' and last and last.kind=='start':abort(400,'Break already started')
 db.session.add(BreakRecord(user_id=user().id,kind=kind));log('break_'+kind);db.session.commit()
 return redirect(url_for('home'))

@app.route('/availability',methods=['GET','POST'])
@login_required
def availability():
 if request.method=='POST':
  day=date.fromisoformat(request.form['day'])
  if day<date.today()-timedelta(days=2):abort(400)
  row=Availability.query.filter_by(user_id=user().id,day=day).first()
  if not row:row=Availability(user_id=user().id,day=day);db.session.add(row)
  row.available=request.form.get('available')=='yes';row.note=request.form.get('note','')[:300]
  log('availability_updated',str(day));db.session.commit();flash('Availability saved','success')
 return render_template('availability.html',rows=Availability.query.filter_by(user_id=user().id).order_by(Availability.day.desc()).limit(90).all())

@app.route('/leave',methods=['GET','POST'])
@login_required
def leave():
 if request.method=='POST':
  a=date.fromisoformat(request.form['start_day']);b=date.fromisoformat(request.form['end_day'])
  if b<a or (b-a).days>60:abort(400,'Invalid leave dates')
  db.session.add(LeaveRequest(user_id=user().id,start_day=a,end_day=b,kind=request.form.get('kind','other')[:30],reason=request.form.get('reason','')[:500]));log('leave_requested');db.session.commit()
 q=LeaveRequest.query
 if user().role=='employee':q=q.filter_by(user_id=user().id)
 return render_template('leave.html',rows=q.order_by(LeaveRequest.id.desc()).limit(200).all(),names={u.id:u.name for u in User.query.all()})

@app.post('/leave/<int:lid>/review')
@manager_required
def leave_review(lid):
 r=db.get_or_404(LeaveRequest,lid);status=request.form.get('status')
 if status not in ('approved','rejected') or r.status!='pending':abort(400)
 r.status=status;r.reviewer_id=user().id;db.session.add(Notice(user_id=r.user_id,message='Leave request '+status));log('leave_review',str(lid));db.session.commit();return redirect(url_for('leave'))

@app.route('/swaps',methods=['GET','POST'])
@login_required
def swaps():
 if request.method=='POST':
  shift=db.get_or_404(Shift,int(request.form['shift_id']));target=db.get_or_404(User,int(request.form['target_id']))
  if shift.user_id!=user().id or target.id==user().id or not target.active:abort(403)
  db.session.add(SwapRequest(shift_id=shift.id,user_id=user().id,target_id=target.id));db.session.add(Notice(user_id=target.id,message='Shift swap requested; awaiting manager approval'));log('swap_requested');db.session.commit()
 q=SwapRequest.query
 if user().role=='employee':q=q.filter((SwapRequest.user_id==user().id)|(SwapRequest.target_id==user().id))
 return render_template('swaps.html',rows=q.order_by(SwapRequest.id.desc()).limit(150).all(),shifts=Shift.query.filter_by(user_id=user().id).filter(Shift.start_at>now()).all(),employees=User.query.filter_by(active=True).all(),names={u.id:u.name for u in User.query.all()})

@app.post('/swaps/<int:sid>/review')
@manager_required
def swap_review(sid):
 r=db.get_or_404(SwapRequest,sid);status=request.form.get('status')
 if r.status!='pending' or status not in ('approved','rejected'):abort(400)
 shift=db.get_or_404(Shift,r.shift_id)
 if status=='approved':shift.user_id=r.target_id
 r.status=status
 for uid in (r.user_id,r.target_id):db.session.add(Notice(user_id=uid,message='Shift swap '+status))
 log('swap_review',str(sid));db.session.commit();return redirect(url_for('swaps'))

@app.route('/geofence',methods=['GET','POST'])
@admin_required
def geofence():
 if request.method=='POST':
  lat=float(request.form['lat']);lng=float(request.form['lng']);radius=float(request.form['radius']);accuracy=float(request.form['accuracy'])
  if not (-90<=lat<=90 and -180<=lng<=180 and 20<=radius<=5000 and 10<=accuracy<=2000):abort(400)
  policy=request.form.get('policy')
  if policy not in ('review','block'):abort(400)
  for k,v in [('geofence_lat',lat),('geofence_lng',lng),('geofence_radius',radius),('gps_max_accuracy',accuracy),('geofence_policy',policy)]:db.session.merge(Setting(key=k,value=str(v)))
  log('geofence_updated');db.session.commit();flash('Geofence saved','success')
 return render_template('geofence.html',settings={k:get_setting(k,'') for k in ['geofence_lat','geofence_lng','geofence_radius','gps_max_accuracy','geofence_policy']})

@app.route('/contributions',methods=['GET','POST'])
@admin_required
def contributions():
 if request.method=='POST':
  agency=request.form.get('agency')
  if agency not in ('SSS','PHILHEALTH','PAGIBIG'):abort(400)
  low=decimal(request.form['min_comp']);high=decimal(request.form['max_comp']);amount=decimal(request.form['employee_amount']);effective=date.fromisoformat(request.form['effective_from'])
  if low<0 or high<low or amount<0:abort(400)
  db.session.add(PayrollRule(agency=agency,min_comp=low,max_comp=high,employee_amount=amount,effective_from=effective));log('contribution_rule_added',agency);db.session.commit()
 return render_template('contributions.html',rows=PayrollRule.query.order_by(PayrollRule.agency,PayrollRule.effective_from.desc()).all())

@app.get('/payroll.csv')
@manager_required
def payroll_csv():
 out=io.StringIO();w=csv.writer(out);w.writerow(['employee','start','end','status','basic','premiums','overtime','night','allowance','sss','philhealth','pagibig','tax','other','thirteenth_base'])
 for r in Payroll.query.order_by(Payroll.start_day.desc()).limit(10000).all():
  w.writerow([db.session.get(User,r.user_id).name,r.start_day,r.end_day,r.status]+[getattr(r,k) for k in ['basic','premiums','overtime','night','allowance','sss','philhealth','pagibig','tax','other','thirteenth_base']])
 return Response(out.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=payroll.csv'})

@app.get('/timesheets.csv')
@manager_required
def timesheets_csv():
 out=io.StringIO();writer=csv.writer(out);writer.writerow(['employee','kind','utc_time','philippine_time','lat','lng','accuracy_m','geofence_exception','status'])
 for r in Attendance.query.order_by(Attendance.at.desc()).limit(10000).all():
  writer.writerow([db.session.get(User,r.user_id).name,r.kind,r.at,local(r.at),r.lat,r.lng,r.accuracy,r.outside_geofence,r.status])
 return Response(out.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=timesheets.csv'})

@app.get('/manifest.webmanifest')
def manifest():
 return jsonify({'name':'Casa Alejandro Employee Hub','short_name':'Casa Hub','start_url':'/','display':'standalone','background_color':'#ffffff','theme_color':'#174a3a'})

@app.cli.command('init-db')
def init_db():
 db.create_all()
 username=os.getenv('ADMIN_USERNAME','admin');password=os.getenv('ADMIN_PASSWORD','')
 if not User.query.filter_by(role='admin').first():
  if len(password)<12:raise RuntimeError('Set ADMIN_PASSWORD (minimum 12 characters) before init-db')
  db.session.add(User(username=username,name='Casa Alejandro Administrator',password_hash=generate_password_hash(password),role='admin',daily_rate=0))
  db.session.commit()
 # Seed illustrative official 2026 national dates; manager should verify updates.
 seed=[('2026-11-01','All Saints Day','special'),('2026-11-02','All Souls Day','special'),('2026-11-30','Bonifacio Day','regular'),('2026-12-08','Immaculate Conception','special'),('2026-12-24','Christmas Eve','special'),('2026-12-25','Christmas Day','regular'),('2026-12-30','Rizal Day','regular'),('2026-12-31','Last Day of the Year','special')]
 for d,n,k in seed:
  if not Holiday.query.filter_by(day=date.fromisoformat(d)).first():db.session.add(Holiday(day=date.fromisoformat(d),name=n,category=k))
 db.session.commit();print('Database initialized; administrator account available.')

if __name__=='__main__':app.run(debug=os.getenv('FLASK_DEBUG')=='1')
