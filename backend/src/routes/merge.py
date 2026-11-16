from fastapi import APIRouter, Depends
from sqlalchemy import select
from src.config.database import get_db
from src.models import SourceBatch, PublishRecord, Dataset
from src.schemas.merge import SourceBatchInput, ArbitrationInput, PublishInput
from src.middlewares.auth import current_user, can_write
from src.services import merge
from src.services.audit import record
from src.utils.serialization import source_dict, sample_dict, arbitration_dict, publish_dict, dataset_dict
router=APIRouter(prefix='/merge')
@router.get('/overview')
def overview(db=Depends(get_db),u=Depends(current_user)):
    return merge.overview(db)
@router.get('/sources')
def sources(db=Depends(get_db),u=Depends(current_user)):
    return [source_dict(b) for b in db.scalars(select(SourceBatch).order_by(SourceBatch.id.desc()).limit(100))]
@router.post('/sources',status_code=201)
def upload(data:SourceBatchInput,db=Depends(get_db),u=Depends(can_write)):
    b=merge.upload(db,data,u); record(db,u.email,'merge.source',{'id':b.id,'channel':b.channel,'stream':b.stream,'version':b.version,'rows':len(b.records)})
    db.commit(); merge.drain(); return source_dict(b)
@router.get('/samples')
def samples(line:str,db=Depends(get_db),u=Depends(current_user)):
    rows,arbs,summary=merge.samples_view(db,line.strip())
    return {'line':line,'summary':summary,'samples':[sample_dict(s) for s in rows],'arbitrations':[arbitration_dict(a) for a in arbs]}
@router.post('/arbitrations',status_code=201)
def arbitrate(data:ArbitrationInput,db=Depends(get_db),u=Depends(can_write)):
    a=merge.arbitrate(db,data,u); record(db,u.email,'merge.arbitrate',{'id':a.id,'line':a.line,'day':a.day,'field':a.field,'value':a.chosen_value})
    db.commit(); return arbitration_dict(a)
@router.post('/arbitrations/{id}/confirm')
def confirm(id:int,db=Depends(get_db),u=Depends(can_write)):
    a=merge.confirm(db,id,u); record(db,u.email,'merge.confirm',{'id':a.id,'line':a.line,'day':a.day,'field':a.field})
    db.commit(); return arbitration_dict(a)
@router.get('/publishes')
def publishes(line:str,db=Depends(get_db),u=Depends(current_user)):
    out=[]
    for p in db.scalars(select(PublishRecord).where(PublishRecord.line==line.strip()).order_by(PublishRecord.id.desc()).limit(50)):
        d=db.get(Dataset,p.dataset_id)
        out.append(publish_dict(p,d.name if d else None))
    return out
@router.post('/publish')
def publish(data:PublishInput,db=Depends(get_db),u=Depends(can_write)):
    dataset,rec,reused=merge.publish(db,data.line,u)
    record(db,u.email,'merge.publish',{'line':rec.line,'dataset':dataset.id,'reused':reused,'basis':len(rec.basis)})
    db.commit(); return {'dataset':dataset_dict(dataset),'publish':publish_dict(rec,dataset.name),'reused':reused}
