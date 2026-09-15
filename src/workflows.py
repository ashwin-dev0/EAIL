import hashlib, uuid
from src.database import db
from src.logging_setup import now,event
from src.auth import DEPARTMENTS

def propose(principal,department,title,idempotency_key):
    principal.require_department(department)
    if not isinstance(title,str) or not 3<=len(title)<=300: raise ValueError('Title must be 3..300 characters')
    if not isinstance(idempotency_key,str) or not 8<=len(idempotency_key)<=100: raise ValueError('Idempotency key must be 8..100 characters')
    scoped_key=hashlib.sha256((principal.id+':'+idempotency_key).encode()).hexdigest()
    # Unique key handles concurrent duplicate proposals. A repeated key with a
    # different payload is rejected, rather than silently accepting another action.
    old=db.rows('SELECT * FROM eail_actions WHERE idempotency_key=?',(scoped_key,))
    if old:
        if old[0]['title']!=title or old[0]['department']!=department: raise ValueError('Idempotency key payload mismatch')
        return old[0]
    action_id=str(uuid.uuid4());stamp=now()
    try:
        with db.connect() as conn:
            db.execute(conn,'INSERT INTO eail_actions VALUES (?,?,?,?,?,?,?,?,?)',
                (action_id,principal.id,department,title,'pending',scoped_key,None,stamp,stamp))
    except Exception:
        old=db.rows('SELECT * FROM eail_actions WHERE idempotency_key=?',(scoped_key,))
        if old and old[0]['title']==title and old[0]['department']==department: return old[0]
        raise
    event('audit','action_proposed',user_id=principal.id,action_id=action_id,department=department)
    return db.rows('SELECT * FROM eail_actions WHERE id=?',(action_id,))[0]

def approve(principal,action_id):
    if not principal.approve: raise PermissionError('Approval grant required')
    with db.connect() as conn:
        row=db.execute(conn,'SELECT * FROM eail_actions WHERE id=?',(action_id,)).fetchone()
        if not row: raise ValueError('Action unavailable')
        principal.require_department(row['department'])
        if row['requester']==principal.id: raise PermissionError('Self-approval prohibited')
        if row['status']=='executed': return {'id':action_id,'status':'executed','duplicate_prevented':True}
        if row['status']!='pending': raise ValueError('Action cannot be approved')
        changed=db.execute(conn,"UPDATE eail_actions SET status='executing',approver=?,updated_at=? WHERE id=? AND status='pending'",
                           (principal.id,now(),action_id)).rowcount
        if changed!=1: raise ValueError('Concurrent approval; reload status')
        # Concrete implemented action: create a LOCAL follow-up task. External
        # payments/HR mutations require separate enterprise-specific adapters.
        db.execute(conn,'INSERT INTO eail_tasks VALUES (?,?,?,?,?)',
            (str(uuid.uuid4()),action_id,row['department'],row['title'],now()))
        db.execute(conn,"UPDATE eail_actions SET status='executed',updated_at=? WHERE id=?",(now(),action_id))
    event('audit','action_executed',user_id=principal.id,action_id=action_id)
    return {'id':action_id,'status':'executed'}

def list_actions(principal):
    rows=db.rows('SELECT * FROM eail_actions ORDER BY created_at DESC LIMIT 1000')
    return [r for r in rows if r['department'] in principal.departments and
            (r['requester']==principal.id or principal.approve)]
