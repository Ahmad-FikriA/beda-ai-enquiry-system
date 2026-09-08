"""Optional real-provider smoke check. Uses synthetic inputs and a temporary DB.

Run explicitly: uv run --env-file .env python -m tests.check_live_junk
This makes real Gemini requests and may consume provider quota.
"""
import json
import tempfile
from pathlib import Path
from beda.live import LiveService
from beda.storage import Database
from beda.workspace import fixtures


def main():
    cases=[next(row for row in fixtures() if row['id']=='E004'),
        {'id':'NEW-SPAM','from':'seller@example.com','subject':'Promote your website',
         'body':'Buy our bulk advertising contact database today. Discount ends tonight; pay us in cryptocurrency. This is an unsolicited promotion.'},
        {'id':'NEW-SALES','from':'Alex <alex@example.com>','subject':'Solar for our warehouse',
         'body':'Hi BEDA, our warehouse has rising electricity costs. Can you assess rooftop solar? Please tell us what site information you need. Thanks, Alex.'}]
    with tempfile.TemporaryDirectory(prefix='beda-live-junk-check-') as temp:
        db=Database(str(Path(temp)/'check.db'));db.initialize()
        service=LiveService(db)
        outcomes=[]
        for payload in cases:
            eq=service.process_input(payload)
            result={'id':eq.id,'status':eq.status,'category':eq.proposal.category if eq.proposal else None,
                'action':eq.recommendation.action if eq.recommendation else None,'draft':eq.draft_response}
            outcomes.append(result)
            print(json.dumps(result),flush=True)
        valid=all(row['category']=='junk' and row['status'] in ('JUNK','PENDING_APPROVAL') and row['draft'] is None for row in outcomes[:2])
        valid=valid and outcomes[2]['category']=='sales' and outcomes[2]['status']=='PENDING_APPROVAL' and bool(outcomes[2]['draft'])
        if not valid:
            raise SystemExit('Live smoke check did not meet expectations. Inspect output; do not treat offline tests as model-quality evidence.')


if __name__=='__main__':
    main()
