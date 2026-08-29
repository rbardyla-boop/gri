from __future__ import annotations
from sem0r_gen_core import nonce


def lexicon_pair(i: int, invariant: bool):
    verb=nonce('VARK',i); obj=nonce('CUBE',i); pair=f'LEXICON-{i:02d}'; focus=f'{obj} underwent exactly two clockwise rotations.'
    if not invariant and i == 0:
        a=[f'Definition: to {verb} an object means to rotate it exactly twice clockwise.',f'Ada {verb}ed {obj} once.']
        b=[f'Definition: to {verb} an object means to rotate it exactly three times clockwise.',f'Ada {verb}ed {obj} once.']
        pa=[(focus,'ENTAILED',['S1','S2']),(f'{obj} underwent one clockwise rotation.','CONTRADICTED',['S1','S2']),(f'Ada acted on {obj}.','ENTAILED',['S2']),(f'{obj} underwent exactly three clockwise rotations.','CONTRADICTED',['S1','S2']),(f'The rotations were counterclockwise.','CONTRADICTED',['S1']),(f'Ada {verb}ed {obj}.','ASSERTED',['S2'])]
        pb=[(focus,'CONTRADICTED',['S1','S2']),(f'{obj} underwent exactly three clockwise rotations.','ENTAILED',['S1','S2']),(f'Ada acted on {obj}.','ENTAILED',['S2']),(f'The rotations were counterclockwise.','CONTRADICTED',['S1']),(f'Ada {verb}ed {obj}.','ASSERTED',['S2']),(f'{obj} underwent four rotations.','CONTRADICTED',['S1','S2']),(f'The object changed color.','UNKNOWN',[])]
        return pair,'REVISION',(a,pa,0,'vark_two'),(b,pb,0,'vark_three')
    if not invariant:
        adj=nonce('LUM',i); item=nonce('ORB',i); focus2=f'{item} is permitted through the arch.'
        a=[f'Definition: an object is {adj} iff it has exactly one notch.',f'Rule: every {adj} object is permitted through the arch.',f'{item} has exactly one notch.']
        b=[f'Definition: an object is {adj} iff it has exactly two notches.',f'Rule: every {adj} object is permitted through the arch.',f'{item} has exactly one notch.']
        pa=[(focus2,'ENTAILED',['S1','S2','S3']),(f'{item} is {adj}.','ENTAILED',['S1','S3']),(f'{item} has exactly one notch.','ASSERTED',['S3']),(f'{item} has exactly two notches.','CONTRADICTED',['S3']),('Every object is permitted through the arch.','UNKNOWN',[]),(f'{item} is forbidden through the arch.','CONTRADICTED',['S1','S2','S3']),(f'{adj} means “blue”.','CONTRADICTED',['S1'])]
        pb=[(focus2,'UNKNOWN',[]),(f'{item} is {adj}.','CONTRADICTED',['S1','S3']),(f'{item} has exactly one notch.','ASSERTED',['S3']),(f'{item} has exactly two notches.','CONTRADICTED',['S3']),('Every object is permitted through the arch.','UNKNOWN',[]),(f'{item} is forbidden through the arch.','UNKNOWN',[]),(f'Any {adj} object is permitted.','ASSERTED',['S2']),(f'{adj} objects have exactly two notches.','ENTAILED',['S1'])]
        return pair,'REVISION',(a,pa,0,'lum_one_notch'),(b,pb,0,'lum_two_notches')
    if i == 2:
        a=[f'Definition: to {verb} means to rotate exactly twice clockwise.',f'Ada {verb}ed {obj}.']
        b=[f'In this lexicon, {verb} = perform exactly two clockwise rotations.',f'Ada performed the action {verb} on {obj}.']
        pa=[(focus,'ENTAILED',['S1','S2']),(f'Ada acted on {obj}.','ENTAILED',['S2']),(f'{obj} rotated clockwise.','ENTAILED',['S1','S2']),(f'{obj} rotated counterclockwise.','CONTRADICTED',['S1']),(f'{obj} changed color.','UNKNOWN',[]),(f'Ada {verb}ed {obj}.','ASSERTED',['S2'])]
        pb=[(focus,'ENTAILED',['S1','S2']),(f'Ada acted on {obj}.','ENTAILED',['S2']),(f'{obj} rotated clockwise.','ENTAILED',['S1','S2']),(f'{obj} rotated counterclockwise.','CONTRADICTED',['S1']),(f'{obj} changed color.','UNKNOWN',[]),(f'Ada performed {verb} on {obj}.','ASSERTED',['S2'])]
        return pair,'INVARIANCE',(a,pa,0,'definition_plain'),(b,pb,0,'definition_equivalent')
    a=[f'Definition: to {verb} an object means exactly two clockwise rotations.',f'Ada {verb}ed {obj}.','A nearby lamp is off.']
    b=['A nearby lamp is on.',f'Definition: to {verb} an object means exactly two clockwise rotations.',f'Ada {verb}ed {obj}.']
    pa=[(focus,'ENTAILED',['S1','S2']),(f'The lamp is off.','ASSERTED',['S3']),(f'The lamp controls {verb}.','UNKNOWN',[]),(f'{obj} rotated clockwise.','ENTAILED',['S1','S2']),(f'{obj} underwent three clockwise rotations.','CONTRADICTED',['S1','S2']),(f'Ada acted on {obj}.','ENTAILED',['S2']),(f'{obj} is blue.','UNKNOWN',[])]
    pb=[(focus,'ENTAILED',['S2','S3']),(f'The lamp is on.','ASSERTED',['S1']),(f'The lamp controls {verb}.','UNKNOWN',[]),(f'{obj} rotated clockwise.','ENTAILED',['S2','S3']),(f'{obj} underwent three clockwise rotations.','CONTRADICTED',['S2','S3']),(f'Ada acted on {obj}.','ENTAILED',['S3']),(f'{obj} is blue.','UNKNOWN',[])]
    return pair,'INVARIANCE',(a,pa,0,'irrelevant_lamp_off'),(b,pb,0,'irrelevant_lamp_on')


def abductive_pair(i: int, invariant: bool):
    obj=nonce('DAX',i); pair=f'ABDUCT-{i:02d}'; focus=f'{obj} touched copper.'
    if not invariant and i == 0:
        a=[f'Rule: if {obj} touches copper, then {obj} becomes blue.',f'{obj} is blue now.']
        b=[f'Rule: {obj} is blue if and only if {obj} has touched copper.',f'{obj} is blue now.']
        pa=[(focus,'UNKNOWN',[]),(f'{obj} is blue.','ASSERTED',['S2']),(f'Copper contact would be sufficient for blue.','ENTAILED',['S1']),(f'Blue proves copper contact.','CONTRADICTED',['S1']),(f'{obj} did not touch copper.','UNKNOWN',[]),(f'Something made {obj} blue.','UNKNOWN',[]),(f'Copper contact is the only possible cause of blue.','CONTRADICTED',['S1']),(f'{obj} exists.','PRESUPPOSED',['S1','S2'])]
        pb=[(focus,'ENTAILED',['S1','S2']),(f'{obj} is blue.','ASSERTED',['S2']),(f'Copper contact is sufficient for blue.','ENTAILED',['S1']),(f'Blue is sufficient evidence of copper contact under the stated rule.','ENTAILED',['S1','S2']),(f'{obj} did not touch copper.','CONTRADICTED',['S1','S2']),(f'Copper contact is necessary for blue.','ENTAILED',['S1']),(f'{obj} touched iron.','UNKNOWN',[]),(f'{obj} exists.','PRESUPPOSED',['S1','S2'])]
        return pair,'REVISION',(a,pa,0,'one_way_rule'),(b,pb,0,'biconditional_rule')
    if not invariant:
        a=[f'Rule: copper contact always makes {obj} blue.',f'{obj} is blue.',f'Blue can also result from silver contact.']
        b=[f'Rule: copper contact always makes {obj} blue.',f'{obj} is blue.',f'Copper contact is the only way {obj} can become blue.']
        pa=[(focus,'UNKNOWN',[]),(f'{obj} may have touched silver.','UNKNOWN',[]),(f'{obj} is blue.','ASSERTED',['S2']),(f'Copper contact is the unique explanation.','CONTRADICTED',['S3']),(f'{obj} must have touched either copper or silver.','UNKNOWN',[]),(f'Silver can make {obj} blue.','ASSERTED',['S3']),(f'{obj} touched copper and silver.','UNKNOWN',[])]
        pb=[(focus,'ENTAILED',['S2','S3']),(f'{obj} is blue.','ASSERTED',['S2']),(f'Copper contact is the unique permitted cause of blue.','ASSERTED',['S3']),(f'{obj} did not touch copper.','CONTRADICTED',['S2','S3']),(f'{obj} touched silver.','UNKNOWN',[]),(f'Copper contact can make {obj} blue.','ASSERTED',['S1']),(f'{obj} touched copper and silver.','UNKNOWN',[]),(f'{obj} necessarily touched copper.','ENTAILED',['S2','S3'])]
        return pair,'REVISION',(a,pa,0,'multiple_causes'),(b,pb,0,'sole_cause')
    if i == 2:
        a=[f'Whenever {obj} touches copper, it becomes blue.',f'{obj} is blue.']
        b=[f'Copper contact implies that {obj} is blue.',f'{obj} is blue.']
        p=[(focus,'UNKNOWN',[]),(f'{obj} is blue.','ASSERTED',['S2']),(f'Copper contact is sufficient for blue.','ENTAILED',['S1']),(f'Copper contact is necessary for blue.','CONTRADICTED',['S1']),(f'{obj} did not touch copper.','UNKNOWN',[]),(f'Blue alone establishes copper contact.','CONTRADICTED',['S1']),('The rule is one-directional.','ENTAILED',['S1'])]
        return pair,'INVARIANCE',(a,p,0,'if_then_plain'),(b,p,0,'implies_paraphrase')
    a=[f'If {obj} touches copper, it becomes blue.',f'{obj} is blue.','A bell is silent.']
    b=['A bell is ringing.',f'{obj} is blue.',f'If {obj} touches copper, it becomes blue.']
    pa=[(focus,'UNKNOWN',[]),(f'{obj} is blue.','ASSERTED',['S2']),(f'The bell proves copper contact.','UNKNOWN',[]),(f'Copper contact is sufficient for blue.','ENTAILED',['S1']),(f'Copper contact is necessary for blue.','CONTRADICTED',['S1']),('The bell is silent.','ASSERTED',['S3'])]
    pb=[(focus,'UNKNOWN',[]),(f'{obj} is blue.','ASSERTED',['S2']),(f'The bell proves copper contact.','UNKNOWN',[]),(f'Copper contact is sufficient for blue.','ENTAILED',['S3']),(f'Copper contact is necessary for blue.','CONTRADICTED',['S3']),('The bell is ringing.','ASSERTED',['S1'])]
    return pair,'INVARIANCE',(a,pa,0,'irrelevant_bell_silent'),(b,pb,0,'irrelevant_bell_ringing')
