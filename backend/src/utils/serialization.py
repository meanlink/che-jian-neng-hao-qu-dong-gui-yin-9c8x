import hashlib, json
def checksum(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
def dataset_dict(d):
    return {'id':d.id, 'name':d.name, 'source':d.source, 'rows':len(d.records), 'checksum':d.checksum, 'created_at':d.created_at}
def job_dict(j):
    return {k:getattr(j,k) for k in ['id','name','dataset_id','params','status','result','error','approved','created_at','finished_at']}
def report_dict(r):
    return {k:getattr(r,k) for k in ['id','name','job_id','destination','interval_seconds','next_run','enabled']}
def delivery_dict(d):
    return {k:getattr(d,k) for k in ['id','report_id','created_at','checksum','filename','destination']}
def source_dict(b):
    return {'id':b.id,'channel':b.channel,'stream':b.stream,'version':b.version,'name':b.name,'rows':len(b.records),'checksum':b.checksum,'status':b.status,'created_by':b.created_by,'created_at':b.created_at}
def sample_dict(s):
    return {'id':s.id,'line':s.line,'day':s.day,'values':s.values,'provenance':s.provenance,'status':s.status,'published_dataset_id':s.published_dataset_id,'updated_at':s.updated_at}
def arbitration_dict(a):
    return {k:getattr(a,k) for k in ['id','line','day','field','chosen_value','reason','basis','status','decided_by','decided_at','confirmed_at']}
def publish_dict(p,dataset_name=None):
    return {'id':p.id,'dataset_id':p.dataset_id,'dataset':dataset_name,'line':p.line,'group_checksum':p.group_checksum,'basis':p.basis,'created_by':p.created_by,'created_at':p.created_at}
