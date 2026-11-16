"""三路来源汇合：抄表、排产、环境记录按线体与日期合并为日样本。

- 各来源按（渠道, 班组流）独立修订，新版生效即作废旧版；
- 缺项样本待补，同字段异值交人工裁决并保留候选值与来源；
- 裁决绑定当时来源批次版本，上游更新使裁决失效，重新确认后才可发布；
- 发布整组样本与裁决依据在同一事务生效，内容未变时沿用已有样本批次；
- 汇合任务持久化，意外中断后由 worker 恢复，归因试验只读发布后的数据批次。
"""
import logging, math, time
from datetime import date
from fastapi import HTTPException
from sqlalchemy import select, func
from src.config.database import Session
from src.models import Dataset, SourceBatch, MergeSample, Arbitration, MergeTask, PublishRecord
from src.services.business import CHANNELS, MERGE_FIELDS, FIELD_BOUNDS
from src.utils.serialization import checksum


def _norm_day(value):
    try:
        return str(date.fromisoformat(str(value).strip()))
    except ValueError:
        raise HTTPException(422, f'日期 {value!r} 不是有效 ISO 日期') from None


def _norm_records(records, channel):
    fields = CHANNELS[channel]['fields']
    rows, seen = [], set()
    for i, raw in enumerate(records):
        if not isinstance(raw, dict):
            raise HTTPException(422, f'第 {i+1} 行不是 JSON 对象')
        day = _norm_day(raw.get('day', ''))
        line = str(raw.get('line', '')).strip()
        if not 0 < len(line) <= 40:
            raise HTTPException(422, f'第 {i+1} 行线体缺失或超过 40 字')
        if (line, day) in seen:
            raise HTTPException(422, f'第 {i+1} 行 {line} {day} 与前面重复，同一线体日期在一个批次内只能上报一次')
        seen.add((line, day))
        row = {'day': day, 'line': line}
        for f in fields:
            value = raw.get(f)
            try:
                if value is None or value == '' or isinstance(value, bool):
                    raise ValueError()
                value = float(value)
                if not math.isfinite(value):
                    raise ValueError()
            except (TypeError, ValueError, OverflowError):
                raise HTTPException(422, f'第 {i+1} 行字段 {f} 必须为有限数值') from None
            low, high = FIELD_BOUNDS[f]
            if not low <= value <= high:
                raise HTTPException(422, f'第 {i+1} 行字段 {f} 超出业务范围 {low:g}~{high:g}')
            row[f] = value
        rows.append(row)
    return rows


def enqueue(db, keys):
    for line, day in sorted(keys):
        if not db.scalar(select(MergeTask.id).where(MergeTask.line == line, MergeTask.day == day).limit(1)):
            db.add(MergeTask(line=line, day=day, created_at=time.time()))


def upload(db, data, user):
    """登记一路来源批次；同流新版作废旧版，受影响样本键入汇合队列。"""
    if data.channel not in CHANNELS:
        raise HTTPException(422, '未知资料渠道，仅支持抄表、排产、环境记录')
    stream = data.stream.strip()
    if len(stream) < 2:
        raise HTTPException(422, '上报班组名称去除空格后至少需要两个字符')
    rows = _norm_records(data.records, data.channel)
    prev = db.scalar(select(SourceBatch).where(SourceBatch.channel == data.channel, SourceBatch.stream == stream, SourceBatch.status == 'active'))
    version = (db.scalar(select(func.max(SourceBatch.version)).where(SourceBatch.channel == data.channel, SourceBatch.stream == stream)) or 0) + 1
    keys = {(r['line'], r['day']) for r in rows}
    if prev:
        prev.status = 'superseded'
        keys |= {(r['line'], r['day']) for r in prev.records}
    name = data.name.strip() or f"{CHANNELS[data.channel]['label']}·{stream}·第{version}版"
    batch = SourceBatch(channel=data.channel, stream=stream, version=version, name=name, records=rows, checksum=checksum(rows), status='active', created_by=user.email, created_at=time.time())
    db.add(batch)
    db.flush()
    enqueue(db, keys)
    return batch


def _context(db):
    """当前生效来源的 (线体,日期)→字段候选 索引，以及全部裁决。"""
    idx = {}
    for b in db.scalars(select(SourceBatch).where(SourceBatch.status == 'active')):
        for r in b.records:
            slot = idx.setdefault((r['line'], r['day']), {f: [] for f in MERGE_FIELDS})
            for f in CHANNELS[b.channel]['fields']:
                slot[f].append({'batch_id': b.id, 'stream': b.stream, 'channel': b.channel, 'version': b.version, 'value': r[f]})
    arbs = {(a.line, a.day, a.field): a for a in db.scalars(select(Arbitration))}
    return idx, arbs


def _recompute(db, idx, arbs, line, day):
    """重算一个样本键：聚合候选、校验裁决时效、推导状态。幂等，可重复执行。"""
    cand = idx.get((line, day))
    sample = db.scalar(select(MergeSample).where(MergeSample.line == line, MergeSample.day == day))
    if cand is None:
        if sample:
            db.delete(sample)
        return
    values, provenance, missing, conflicts = {}, {}, [], []
    for f in MERGE_FIELDS:
        cands = cand[f]
        distinct = {c['value'] for c in cands}
        arb = arbs.get((line, day, f))
        if not cands:
            missing.append(f)
            values[f] = None
            provenance[f] = {'candidates': [], 'resolved_by': None, 'arbitration_id': arb.id if arb else None}
        elif len(distinct) == 1:
            values[f] = cands[0]['value']
            provenance[f] = {'candidates': cands, 'resolved_by': 'auto', 'arbitration_id': arb.id if arb else None}
        else:
            current_ids = sorted(c['batch_id'] for c in cands)
            bound_ids = sorted(c['batch_id'] for c in (arb.basis.get('candidates', []) if arb else []))
            if arb and arb.status == 'valid' and bound_ids == current_ids and arb.chosen_value in distinct:
                values[f] = arb.chosen_value
                provenance[f] = {'candidates': cands, 'resolved_by': 'arbitration', 'arbitration_id': arb.id}
            else:
                if arb and arb.status == 'valid':
                    arb.status = 'stale'  # 上游来源版本已变，原裁决失效
                conflicts.append(f)
                values[f] = None
                provenance[f] = {'candidates': cands, 'resolved_by': None, 'arbitration_id': arb.id if arb else None}
    if missing:
        status = 'pending_fill'
    elif conflicts:
        status = 'pending_arbitration'
    else:
        status = 'publishable'
    content = {f: values[f] for f in MERGE_FIELDS}
    content.update({'day': day, 'line': line})
    content_checksum = checksum(content)
    if sample is None:
        sample = MergeSample(line=line, day=day)
        db.add(sample)
    sample.values = values
    sample.provenance = provenance
    sample.content_checksum = content_checksum
    sample.updated_at = time.time()
    if status == 'publishable' and sample.published_checksum == content_checksum:
        status = 'published'
    sample.status = status


def process_tasks(db, limit=500, line=None):
    """消化汇合队列；任务行随处理删除，崩溃遗留的任务下次继续。"""
    q = select(MergeTask).order_by(MergeTask.id).limit(limit)
    if line is not None:
        q = select(MergeTask).where(MergeTask.line == line).order_by(MergeTask.id).limit(limit)
    tasks = db.scalars(q).all()
    if not tasks:
        return 0
    idx, arbs = _context(db)
    for t in tasks:
        _recompute(db, idx, arbs, t.line, t.day)
        db.delete(t)
    return len(tasks)


def drain(limit=5000):
    """请求内尽力汇合；失败由 worker 兜底恢复。"""
    try:
        with Session() as db:
            process_tasks(db, limit)
            db.commit()
    except Exception:
        logging.exception('汇合处理中断，待处理任务将由后台 worker 恢复')


def arbitrate(db, data, user):
    """人工裁决异值字段：从当前候选中取值，绑定当时来源批次版本。"""
    if data.field not in MERGE_FIELDS:
        raise HTTPException(422, '未知字段')
    line, day = data.line.strip(), _norm_day(data.day)
    reason = data.reason.strip()
    if len(reason) < 2:
        raise HTTPException(422, '请填写裁决理由，便于追溯')
    idx, arbs = _context(db)
    cand = idx.get((line, day))
    cands = cand[data.field] if cand else []
    distinct = {c['value'] for c in cands}
    if len(distinct) < 2:
        raise HTTPException(409, '该字段当前没有异值冲突，无需裁决')
    if data.chosen_value not in distinct:
        raise HTTPException(422, '裁决值必须来自当前候选值')
    arb = arbs.get((line, day, data.field))
    now = time.time()
    if arb is None:
        arb = Arbitration(line=line, day=day, field=data.field, decided_at=now)
        db.add(arb)
    arb.chosen_value = data.chosen_value
    arb.reason = reason
    arb.basis = {'candidates': cands}
    arb.status = 'valid'
    arb.decided_by = user.email
    arb.confirmed_at = now
    db.flush()
    arbs[(line, day, data.field)] = arb
    _recompute(db, idx, arbs, line, day)
    return arb


def confirm(db, arbitration_id, user):
    """上游更新后重新确认原裁决：原值仍在候选中才允许沿用。"""
    arb = db.get(Arbitration, arbitration_id)
    if not arb:
        raise HTTPException(404, '裁决记录不存在')
    idx, arbs = _context(db)
    cand = idx.get((arb.line, arb.day))
    cands = cand[arb.field] if cand else []
    distinct = {c['value'] for c in cands}
    if len(distinct) < 2:
        raise HTTPException(409, '上游来源已一致，冲突不复存在，无需重新确认')
    if arb.chosen_value not in distinct:
        raise HTTPException(422, '原裁决值已不在当前候选中，请重新裁决')
    arb.basis = {'candidates': cands}
    arb.status = 'valid'
    arb.confirmed_at = time.time()
    db.flush()
    _recompute(db, idx, arbs, arb.line, arb.day)
    return arb


def publish(db, line, user):
    """整组发布：样本与裁决依据同一事务生效；内容未变时沿用已有样本批次。"""
    line = line.strip()
    if not line:
        raise HTTPException(422, '请指定要发布的线体')
    process_tasks(db, limit=5000, line=line)  # 先消化该线体在途补报，与发布同事务生效
    db.flush()
    samples = db.scalars(select(MergeSample).where(MergeSample.line == line).order_by(MergeSample.day).with_for_update()).all()
    if len(samples) < 5:
        raise HTTPException(422, '该线体汇合样本不足 5 条，暂不能发布')
    blocking = [s for s in samples if s.status in ('pending_fill', 'pending_arbitration')]
    if blocking:
        days = '、'.join(f"{s.day}({'待补齐' if s.status == 'pending_fill' else '待裁决'})" for s in blocking[:8])
        raise HTTPException(409, f'尚有 {len(blocking)} 条样本未就绪：{days}{" 等" if len(blocking) > 8 else ""}，请先补齐或裁决后再发布')
    records = [{'day': s.day, 'line': s.line, **{f: s.values[f] for f in MERGE_FIELDS}} for s in samples]
    arb_ids = sorted({p['arbitration_id'] for s in samples for p in s.provenance.values() if p.get('resolved_by') == 'arbitration' and p.get('arbitration_id')})
    basis = []
    for aid in arb_ids:
        a = db.get(Arbitration, aid)
        if a and a.status == 'valid':
            basis.append({'arbitration_id': a.id, 'day': a.day, 'field': a.field, 'chosen_value': a.chosen_value, 'reason': a.reason, 'decided_by': a.decided_by, 'confirmed_at': a.confirmed_at, 'candidates': a.basis.get('candidates', [])})
    group_checksum = checksum({'records': records, 'basis': basis})
    last = db.scalar(select(PublishRecord).where(PublishRecord.line == line).order_by(PublishRecord.id.desc()).limit(1))
    if last and last.group_checksum == group_checksum:
        dataset = db.get(Dataset, last.dataset_id)
        if dataset:
            for s in samples:
                s.published_checksum, s.published_dataset_id, s.status = s.content_checksum, dataset.id, 'published'
            return dataset, last, True
    seq = (db.scalar(select(func.count()).select_from(PublishRecord).where(PublishRecord.line == line)) or 0) + 1
    dataset = Dataset(name=f'汇合·{line}·{samples[0].day}~{samples[-1].day}·v{seq}', source=f'三路汇合·{line}', records=records, checksum=checksum(records), created_at=time.time())
    db.add(dataset)
    db.flush()
    rec = PublishRecord(dataset_id=dataset.id, line=line, group_checksum=group_checksum, basis=basis, created_by=user.email, created_at=time.time())
    db.add(rec)
    db.flush()
    for s in samples:
        s.published_checksum, s.published_dataset_id, s.status = s.content_checksum, dataset.id, 'published'
    return dataset, rec, False


def overview(db):
    lines = {}
    for s in db.scalars(select(MergeSample)):
        slot = lines.setdefault(s.line, {'line': s.line, 'total': 0, 'pending_fill': 0, 'pending_arbitration': 0, 'publishable': 0, 'published': 0})
        slot['total'] += 1
        slot[s.status] = slot.get(s.status, 0) + 1
    for slot in lines.values():
        last = db.scalar(select(PublishRecord).where(PublishRecord.line == slot['line']).order_by(PublishRecord.id.desc()).limit(1))
        slot['last_publish_at'] = last.created_at if last else None
        slot['dataset_id'] = last.dataset_id if last else None
    return {'lines': sorted(lines.values(), key=lambda x: x['line']), 'pending_tasks': db.scalar(select(func.count()).select_from(MergeTask)) or 0, 'active_sources': db.scalar(select(func.count()).select_from(SourceBatch).where(SourceBatch.status == 'active')) or 0}


def samples_view(db, line):
    samples = db.scalars(select(MergeSample).where(MergeSample.line == line).order_by(MergeSample.day).limit(2000)).all()
    arbs = db.scalars(select(Arbitration).where(Arbitration.line == line).order_by(Arbitration.day)).all()
    summary = {'total': len(samples), 'pending_fill': 0, 'pending_arbitration': 0, 'publishable': 0, 'published': 0}
    for s in samples:
        summary[s.status] += 1
    return samples, arbs, summary
