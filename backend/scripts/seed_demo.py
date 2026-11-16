import time, json, math, random
from datetime import date, timedelta
from sqlalchemy import select, func
from src.config.database import Session
from migrations.initial import migrate
from src.models import User, Dataset, Job, Report, Delivery, Audit, SourceBatch, MergeSample, Arbitration, MergeTask, PublishRecord
from src.services.business import metadata, seed_records, analyze
from src.services.reports import deliver
from src.services import merge as merge_svc
from src.utils.security import hash_password
from src.utils.serialization import checksum
def seed_merge(db):
    """冲压P02 三路来源演示数据：排产、两路抄表（含异值）、环境（含缺报）。"""
    if db.scalar(select(SourceBatch.id).limit(1)):return
    rng=random.Random(2026)
    start=date(2026,5,1)
    base=[]
    for i in range(160):
        day=str(start+timedelta(days=i))
        units=round(690+150*math.sin(i/9+1.3)+rng.gauss(0,70),1)
        run=round(6.1+units/150+rng.gauss(0,0.5),2)
        temp=round(23+8*math.sin(i/29+0.6)+rng.gauss(0,1.2),2)
        idle=round(rng.uniform(0.4,3.2),2)
        kwh=round(118+units*0.44+run*23+temp*3.8+idle*35+rng.gauss(0,12),2)
        base.append({'day':day,'line':'冲压P02','units':units,'run_hours':run,'temp_c':temp,'idle_hours':idle,'kwh':kwh})
    def rows(*fields,skip=()):
        return [{k:r[k] for k in ('day','line')+fields} for i,r in enumerate(base) if i not in skip]
    conflict=(40,97)
    meter2=[{'day':r['day'],'line':r['line'],'kwh':round(r['kwh']*1.045,2) if i in conflict else r['kwh']} for i,r in enumerate(base)]
    now=time.time()
    batches=[
        SourceBatch(channel='schedule',stream='排产组',version=1,name='排产组·5-10月排产工时',records=rows('units','run_hours','idle_hours'),checksum='',status='active',created_by='seed',created_at=now),
        SourceBatch(channel='meter',stream='抄表一组',version=1,name='抄表一组·主表读数',records=rows('kwh'),checksum='',status='active',created_by='seed',created_at=now),
        SourceBatch(channel='meter',stream='抄表二组',version=1,name='抄表二组·复抄读数',records=meter2,checksum='',status='active',created_by='seed',created_at=now),
        SourceBatch(channel='env',stream='环境组',version=1,name='环境组·车间温度记录',records=rows('temp_c',skip=(120,121)),checksum='',status='active',created_by='seed',created_at=now),
    ]
    for b in batches:b.checksum=checksum(b.records)
    db.add_all(batches);db.flush()
    m1,m2=batches[1],batches[2]
    day40=base[40]['day']
    db.add(Arbitration(line='冲压P02',day=day40,field='kwh',chosen_value=base[40]['kwh'],reason='一组为主表，二组当日表计电池亏电抄见数偏高约4.5%，复核以一组读数为准。',basis={'candidates':[{'batch_id':m1.id,'stream':'抄表一组','channel':'meter','version':1,'value':base[40]['kwh']},{'batch_id':m2.id,'stream':'抄表二组','channel':'meter','version':1,'value':meter2[40]['kwh']}]},status='valid',decided_by='admin@demo.local',decided_at=now,confirmed_at=now))
    merge_svc.enqueue(db,{(r['line'],r['day']) for r in base})
    db.flush()
    merge_svc.process_tasks(db,limit=5000)
    db.add(Audit(actor='seed',action='demo.merge',detail={'line':'冲压P02','days':len(base)},at=now))
def seed():
    migrate()
    with Session() as db:
        for role,name in [('admin','林知 · 业务负责人'),('analyst','陈舟 · 分析员'),('viewer','周禾 · 观察员')]:
            email=role+'@demo.local'
            if not db.scalar(select(User).where(User.email==email)):
                db.add(User(email=email,name=name,role=role,password=hash_password('Demo123!')))
        db.flush()
        m=metadata()
        d=db.scalar(select(Dataset).where(Dataset.name==m['dataset_name']))
        if not d:
            rows=seed_records()
            d=Dataset(name=m['dataset_name'],source=m['short']+'-202611.csv',records=rows,checksum=checksum(rows),created_at=time.time())
            db.add(d); db.flush()
        if not db.scalar(select(Job).where(Job.name=='基线复核 · '+m['name'])):
            params={p['key']:p['default'] for p in m.get('parameters',[])}
            result=analyze(d.records,params)
            json.dumps(result,ensure_ascii=False,allow_nan=False)
            admin=db.scalar(select(User).where(User.role=='admin'))
            j=Job(name='基线复核 · '+m['name'],dataset_id=d.id,params=params,status='completed',result=result,created_by=admin.id,created_at=time.time()-3600,finished_at=time.time()-3595,approved=True)
            db.add(j);db.flush()
            r=Report(name='每日业务复核简报',job_id=j.id,destination='业务复核组 · 本地收件箱',interval_seconds=86400,next_run=time.time()+86400,enabled=True)
            db.add(r);db.flush();deliver(db,r)
            db.add(Audit(actor='seed',action='demo.baseline',detail={'dataset':d.id},at=time.time()))
        seed_merge(db)
        db.commit()
        counts={model.__tablename__:db.scalar(select(func.count()).select_from(model)) for model in [User,Dataset,Job,Report,Delivery,Audit,SourceBatch,MergeSample,Arbitration,MergeTask,PublishRecord]}
        print(json.dumps(counts,ensure_ascii=False))
        return counts
if __name__=='__main__':seed()
