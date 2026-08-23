from __future__ import annotations
from sem0r_gen_core import nonce


def _trim(props, n):
    return props[:n]


def release_pair(i: int, invariant: bool):
    gate = nonce('GATE', i); aux = nonce('AUX', i); pair=f'RELEASE-{i:02d}'
    focus='The release conditions are satisfied.'
    if not invariant and i == 0:
        a=[f'{gate} passed.','Release policy: release is permitted exactly when GATE passes.']
        b=[f'{gate} passed.',f'{aux} failed.','Release policy: both GATE and AUX are mandatory and both must pass.']
        pa=[(focus,'ENTAILED',['S1','S2']),(f'{gate} passed.','ASSERTED',['S1']),(f'{aux} passed.','UNKNOWN',[]),(f'{aux} failed.','UNKNOWN',[]),('Every possible safety requirement passed.','UNKNOWN',[]),('The released system is safe in every respect.','UNKNOWN',[])]
        pb=[(focus,'CONTRADICTED',['S2','S3']),(f'{gate} passed.','ASSERTED',['S1']),(f'{aux} failed.','ASSERTED',['S2']),('Release is forbidden.','ENTAILED',['S2','S3']),(f'{aux} passed.','CONTRADICTED',['S2']),('At least one mandatory gate failed.','ENTAILED',['S2','S3']),('Every possible safety requirement passed.','UNKNOWN',[])]
        return pair,'REVISION',(a,pa,0,'single_gate_pass'),(b,pb,0,'second_mandatory_failure')
    if not invariant:
        a=[f'{gate} passed.',f'{aux} failed.','Policy: AUX is diagnostic only; GATE alone controls release.']
        b=[f'{gate} passed.',f'{aux} failed.','Policy: AUX is mandatory; a failed AUX blocks release.']
        pa=[(focus,'ENTAILED',['S1','S3']),(f'{aux} blocks release.','CONTRADICTED',['S3']),(f'{aux} failed.','ASSERTED',['S2']),(f'{gate} passed.','ASSERTED',['S1']),('Release is blocked.','CONTRADICTED',['S1','S3']),('The diagnostic result is favorable.','UNKNOWN',[]),('GATE controls release.','ENTAILED',['S3'])]
        pb=[(focus,'CONTRADICTED',['S2','S3']),(f'{aux} blocks release.','ENTAILED',['S2','S3']),(f'{aux} failed.','ASSERTED',['S2']),(f'{gate} passed.','ASSERTED',['S1']),('Release is blocked.','ENTAILED',['S2','S3']),('GATE failed.','CONTRADICTED',['S1']),('AUX is merely diagnostic.','CONTRADICTED',['S3']),('Every mandatory condition passed.','CONTRADICTED',['S2','S3'])]
        return pair,'REVISION',(a,pa,0,'diagnostic_aux'),(b,pb,0,'mandatory_aux')
    if i == 2:
        a=[f'{gate} passed.','Policy: release occurs if and only if GATE passes.']
        b=[f'The result for {gate} was a pass.','Under policy, passing GATE is necessary and sufficient for release.']
        pa=[(focus,'ENTAILED',['S1','S2']),(f'{gate} passed.','ASSERTED',['S1']),('Release is blocked.','CONTRADICTED',['S1','S2']),('A separate unnamed gate failed.','UNKNOWN',[]),('The released system can never fail later.','UNKNOWN',[])]
        pb=[(focus,'ENTAILED',['S1','S2']),(f'{gate} passed.','ASSERTED',['S1']),('Release is blocked.','CONTRADICTED',['S1','S2']),('The policy makes GATE sufficient.','ENTAILED',['S2']),('The released system can never fail later.','UNKNOWN',[])]
        return pair,'INVARIANCE',(a,pa,0,'iff_plain'),(b,pb,0,'iff_paraphrase')
    a=[f'{gate} passed.','Policy: GATE is the only release gate.','The operator wore a green badge.']
    b=[f'{gate} passed.','The operator wore a blue badge.','Policy: GATE is the only release gate.']
    pa=[(focus,'ENTAILED',['S1','S2']),(f'{gate} passed.','ASSERTED',['S1']),('The badge color controls release.','CONTRADICTED',['S2','S3']),(f'{gate} failed.','CONTRADICTED',['S1']),('The operator wore a green badge.','ASSERTED',['S3']),('Another mandatory gate exists.','CONTRADICTED',['S2'])]
    pb=[(focus,'ENTAILED',['S1','S3']),(f'{gate} passed.','ASSERTED',['S1']),('The badge color controls release.','CONTRADICTED',['S2','S3']),(f'{gate} failed.','CONTRADICTED',['S1']),('The operator wore a blue badge.','ASSERTED',['S2']),('Another mandatory gate exists.','CONTRADICTED',['S3'])]
    return pair,'INVARIANCE',(a,pa,0,'irrelevant_green'),(b,pb,0,'irrelevant_blue')


def temporal_pair(i: int, invariant: bool):
    obj=nonce('DAX',i); pair=f'TEMPORAL-{i:02d}'; focus=f'{obj} is blue now.'
    if not invariant and i == 0:
        a=[f'Rule: whenever {obj} touches copper, it becomes blue for exactly ten minutes, starting immediately.',f'{obj} touched copper six minutes ago.',f'No other color-changing rule applies to {obj}.']
        b=[f'Rule: whenever {obj} touches copper, it becomes blue for exactly ten minutes, starting immediately.',f'{obj} touched copper twelve minutes ago.',f'No other color-changing rule applies to {obj}.']
        pa=[(focus,'ENTAILED',['S1','S2']), (f'{obj} touched copper.','ASSERTED',['S2']), (f'{obj} must remain blue six minutes from now.','CONTRADICTED',['S1','S2']), (f'{obj} is red now.','UNKNOWN',[]), (f'Copper contact is the only possible cause of blue color.','UNKNOWN',[]), (f'{obj} existed before copper contact.','UNKNOWN',[]), (f'{obj} will be blue exactly twenty minutes after contact.','CONTRADICTED',['S1'])]
        pb=[(focus,'CONTRADICTED',['S1','S2','S3']), (f'{obj} touched copper.','ASSERTED',['S2']), (f'{obj} was blue five minutes after contact.','ENTAILED',['S1','S2']), (f'The ten-minute copper effect has ended.','ENTAILED',['S1','S2']), (f'{obj} is red now.','UNKNOWN',[]), (f'{obj} was blue eleven minutes after contact.','CONTRADICTED',['S1']), (f'{obj} cannot ever become blue again.','UNKNOWN',[])]
        return pair,'REVISION',(a,pa,0,'six_minutes'),(b,pb,0,'twelve_minutes')
    if not invariant:
        a=[f'Rule: copper contact makes {obj} blue for exactly ten minutes.',f'{obj} touched copper twelve minutes ago.',f'No other color-changing rule applies.']
        b=[f'Rule: copper contact makes {obj} blue for exactly fifteen minutes.',f'{obj} touched copper twelve minutes ago.',f'No other color-changing rule applies.']
        pa=[(focus,'CONTRADICTED',['S1','S2','S3']),(f'The copper effect has ended.','ENTAILED',['S1','S2']),(f'{obj} touched copper.','ASSERTED',['S2']),(f'{obj} was blue eight minutes after contact.','ENTAILED',['S1','S2']),(f'{obj} is green now.','UNKNOWN',[]),(f'{obj} is still under the copper effect.','CONTRADICTED',['S1','S2']),(f'Copper contact occurred exactly twelve minutes ago.','ASSERTED',['S2'])]
        pb=[(focus,'ENTAILED',['S1','S2']),(f'The copper effect has ended.','CONTRADICTED',['S1','S2']),(f'{obj} touched copper.','ASSERTED',['S2']),(f'{obj} was blue eight minutes after contact.','ENTAILED',['S1','S2']),(f'{obj} is green now.','CONTRADICTED',['S1','S2']),(f'{obj} is still under the copper effect.','ENTAILED',['S1','S2']),(f'Copper contact occurred exactly twelve minutes ago.','ASSERTED',['S2']),(f'The effect lasts exactly fifteen minutes.','ASSERTED',['S1'])]
        return pair,'REVISION',(a,pa,0,'duration_ten'),(b,pb,0,'duration_fifteen')
    if i == 2:
        a=[f'Rule: after touching copper, {obj} is blue for exactly ten minutes.',f'{obj} made copper contact four minutes ago.']
        b=[f'Rule: copper contact immediately starts a ten-minute interval during which {obj} is blue.',f'Four minutes have elapsed since {obj} touched copper.']
        pa=[(focus,'ENTAILED',['S1','S2']),(f'{obj} touched copper.','ASSERTED',['S2']),(f'The copper effect is active now.','ENTAILED',['S1','S2']),(f'{obj} will necessarily be blue seven minutes from now.','CONTRADICTED',['S1','S2']),(f'{obj} was blue two minutes after contact.','ENTAILED',['S1','S2']),(f'No other mechanism can make {obj} blue.','UNKNOWN',[])]
        pb=[(focus,'ENTAILED',['S1','S2']),(f'{obj} touched copper.','ASSERTED',['S2']),(f'The copper effect is active now.','ENTAILED',['S1','S2']),(f'The effect has already ended.','CONTRADICTED',['S1','S2']),(f'{obj} will necessarily be blue seven minutes from now.','CONTRADICTED',['S1','S2']),(f'{obj} was blue two minutes after contact.','ENTAILED',['S1','S2']),(f'No other mechanism can make {obj} blue.','UNKNOWN',[])]
        return pair,'INVARIANCE',(a,pa,0,'temporal_plain'),(b,pb,0,'temporal_paraphrase')
    a=[f'Rule: copper contact makes {obj} blue for exactly ten minutes.',f'{obj} touched copper three minutes ago.',f'{obj} weighs 14 glim.']
    b=[f'{obj} weighs 23 glim.',f'{obj} touched copper three minutes ago.',f'Rule: copper contact makes {obj} blue for exactly ten minutes.']
    pa=[(focus,'ENTAILED',['S1','S2']),(f'{obj} touched copper.','ASSERTED',['S2']),(f'{obj} weighs 14 glim.','ASSERTED',['S3']),(f'The blue interval is active.','ENTAILED',['S1','S2']),(f'{obj} is necessarily blue eleven minutes after contact.','CONTRADICTED',['S1']),(f'The weight determines the color rule.','UNKNOWN',[]),(f'{obj} did not touch copper.','CONTRADICTED',['S2'])]
    pb=[(focus,'ENTAILED',['S2','S3']),(f'{obj} touched copper.','ASSERTED',['S2']),(f'{obj} weighs 23 glim.','ASSERTED',['S1']),(f'The blue interval is active.','ENTAILED',['S2','S3']),(f'{obj} is necessarily blue eleven minutes after contact.','CONTRADICTED',['S3']),(f'The weight determines the color rule.','UNKNOWN',[]),(f'{obj} did not touch copper.','CONTRADICTED',['S2'])]
    return pair,'INVARIANCE',(a,pa,0,'irrelevant_weight_a'),(b,pb,0,'irrelevant_weight_b')
