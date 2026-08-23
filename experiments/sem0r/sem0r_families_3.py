from __future__ import annotations
from sem0r_gen_core import nonce


def deixis_pair(i: int, invariant: bool):
    blue=nonce('BLUECUBE',i); red=nonce('REDSPHERE',i); pair=f'DEIXIS-{i:02d}'; focus=f'{blue} is the object the speaker refers to as “that”.'
    if not invariant and i == 0:
        a=[f'Two objects are present: {blue} and {red}.',f'The speaker points directly at {blue} and says, “Move that to Bay 2.”']
        b=[f'Two objects are present: {blue} and {red}.',f'The speaker points directly at {red} and says, “Move that to Bay 2.”']
        pa=[(focus,'ENTAILED',['S2']),(f'{red} is the referent of “that”.','CONTRADICTED',['S2']),(f'{blue} should be moved to Bay 2.','ENTAILED',['S2']),(f'{red} should be moved to Bay 2.','CONTRADICTED',['S2']),('Bay 2 is occupied.','UNKNOWN',[]),(f'{blue} is blue.','UNKNOWN',[]),(f'The speaker pointed at {blue}.','ASSERTED',['S2'])]
        pb=[(focus,'CONTRADICTED',['S2']),(f'{red} is the referent of “that”.','ENTAILED',['S2']),(f'{blue} should be moved to Bay 2.','CONTRADICTED',['S2']),(f'{red} should be moved to Bay 2.','ENTAILED',['S2']),('Bay 2 is occupied.','UNKNOWN',[]),(f'The speaker pointed at {red}.','ASSERTED',['S2'])]
        return pair,'REVISION',(a,pa,0,'point_blue'),(b,pb,0,'point_red')
    if not invariant:
        person=nonce('NIA',i); other=nonce('SOL',i); item=nonce('ORBIT',i); focus2=f'The pronoun “she” refers to {person}.'
        a=[f'{person} and {other} are in the room.',f'Immediately before the utterance, {person} is designated as the current speaker.',f'The log says: “She will carry {item}.”']
        b=[f'{person} and {other} are in the room.',f'Immediately before the utterance, {other} is designated as the current speaker.',f'The log convention says first-person-role reports use “she” for the designated current speaker.',f'The log says: “She will carry {item}.”']
        pa=[(focus2,'UNKNOWN',[]),(f'{person} will carry {item}.','UNKNOWN',[]),(f'{other} will carry {item}.','UNKNOWN',[]),(f'Someone will carry {item}.','ENTAILED',['S3']),(f'{person} is the current speaker.','ASSERTED',['S2']),(f'{other} is the current speaker.','CONTRADICTED',['S2']),('The pronoun has only one linguistically possible referent.','UNKNOWN',[])]
        pb=[(focus2,'CONTRADICTED',['S2','S3']),(f'{other} will carry {item}.','ENTAILED',['S2','S3','S4']),(f'{person} will carry {item}.','CONTRADICTED',['S2','S3']),(f'Someone will carry {item}.','ENTAILED',['S4']),(f'{other} is the current speaker.','ASSERTED',['S2']),(f'The reporting convention resolves “she”.','ENTAILED',['S3']),(f'{item} will be destroyed.','UNKNOWN',[]),(f'{person} is the current speaker.','CONTRADICTED',['S2'])]
        return pair,'REVISION',(a,pa,0,'ambiguous_pronoun'),(b,pb,0,'convention_resolves')
    if i == 2:
        a=[f'The only objects on the table are {blue} and {red}.',f'The speaker taps {blue} while saying, “Inspect that.”']
        b=[f'On the table there are exactly two objects, {blue} and {red}.',f'While saying “Inspect that,” the speaker taps {blue}.']
        pa=[(focus,'ENTAILED',['S2']),(f'{blue} is to be inspected.','ENTAILED',['S2']),(f'{red} is to be inspected.','CONTRADICTED',['S2']),(f'The table has exactly two objects.','ASSERTED',['S1']),(f'{red} is absent.','CONTRADICTED',['S1']),('The inspection has already happened.','UNKNOWN',[])]
        pb=[(focus,'ENTAILED',['S2']),(f'{blue} is to be inspected.','ENTAILED',['S2']),(f'{red} is to be inspected.','CONTRADICTED',['S2']),(f'The table has exactly two objects.','ASSERTED',['S1']),(f'{red} is absent.','CONTRADICTED',['S1']),('The inspection has already happened.','UNKNOWN',[])]
        return pair,'INVARIANCE',(a,pa,0,'tap_plain'),(b,pb,0,'tap_paraphrase')
    a=[f'The speaker points to {blue} and says, “Store that.”','A bell rings once.']
    b=['A bell rings twice.',f'The speaker points to {blue} and says, “Store that.”']
    pa=[(focus,'ENTAILED',['S1']),(f'{blue} is to be stored.','ENTAILED',['S1']),(f'The bell determines the referent.','UNKNOWN',[]),(f'The bell rang once.','ASSERTED',['S2']),(f'{red} is the referent.','CONTRADICTED',['S1']),('Storage has already completed.','UNKNOWN',[]),(f'The speaker pointed to {blue}.','ASSERTED',['S1'])]
    pb=[(focus,'ENTAILED',['S2']),(f'{blue} is to be stored.','ENTAILED',['S2']),(f'The bell determines the referent.','UNKNOWN',[]),(f'The bell rang twice.','ASSERTED',['S1']),(f'{red} is the referent.','CONTRADICTED',['S2']),('Storage has already completed.','UNKNOWN',[]),(f'The speaker pointed to {blue}.','ASSERTED',['S2'])]
    return pair,'INVARIANCE',(a,pa,0,'irrelevant_bell_one'),(b,pb,0,'irrelevant_bell_two')


def quant_pair(i: int, invariant: bool):
    group=nonce('ZOR',i); pair=f'QUANT-{i:02d}'; focus=f'Every {group} passed.'
    if not invariant and i == 0:
        a=[f'Every {group} passed.',f'There are three {group}s.']
        b=[f'Some {group}s passed and some {group}s failed.',f'There are three {group}s.']
        pa=[(focus,'ASSERTED',['S1']),(f'At least one {group} passed.','ENTAILED',['S1','S2']),(f'No {group} failed.','ENTAILED',['S1']),(f'Exactly three {group}s passed.','ENTAILED',['S1','S2']),(f'Some {group} failed.','CONTRADICTED',['S1']),(f'Exactly four {group}s exist.','CONTRADICTED',['S2']),(f'At least one {group} failed.','CONTRADICTED',['S1'])]
        pb=[(focus,'CONTRADICTED',['S1']),(f'At least one {group} passed.','ENTAILED',['S1']),(f'At least one {group} failed.','ENTAILED',['S1']),(f'No {group} failed.','CONTRADICTED',['S1']),(f'Exactly three {group}s exist.','ASSERTED',['S2']),(f'Exactly one {group} failed.','UNKNOWN',[])]
        return pair,'REVISION',(a,pa,0,'universal'),(b,pb,0,'mixed')
    if not invariant:
        focus2=f'No {group} passed.'
        a=[f'Not every {group} passed.',f'At least one {group} exists.']
        b=[f'No {group} passed.',f'At least one {group} exists.']
        pa=[(focus2,'UNKNOWN',[]),(f'At least one {group} failed.','ENTAILED',['S1']),(f'At least one {group} passed.','UNKNOWN',[]),(f'Every {group} passed.','CONTRADICTED',['S1']),(f'Some {group} exists.','ASSERTED',['S2']),(f'Exactly one {group} failed.','UNKNOWN',[])]
        pb=[(focus2,'ASSERTED',['S1']),(f'At least one {group} failed.','ENTAILED',['S1','S2']),(f'At least one {group} passed.','CONTRADICTED',['S1']),(f'Every {group} passed.','CONTRADICTED',['S1','S2']),(f'Some {group} exists.','ASSERTED',['S2']),(f'All {group}s failed.','ENTAILED',['S1']),(f'Exactly one {group} failed.','UNKNOWN',[])]
        return pair,'REVISION',(a,pa,0,'not_every'),(b,pb,0,'none')
    if i == 2:
        a=[f'Every one of the four {group}s passed.']
        b=[f'All four {group}s passed.']
        pa=[(focus,'ASSERTED',['S1']),(f'At least one {group} passed.','ENTAILED',['S1']),(f'Exactly four {group}s passed.','ENTAILED',['S1']),(f'Some {group} failed.','CONTRADICTED',['S1']),(f'Five {group}s passed.','CONTRADICTED',['S1']),(f'The test was easy.','UNKNOWN',[]),(f'No {group} passed.','CONTRADICTED',['S1'])]
        pb=[(focus,'ASSERTED',['S1']),(f'At least one {group} passed.','ENTAILED',['S1']),(f'Exactly four {group}s passed.','ENTAILED',['S1']),(f'Some {group} failed.','CONTRADICTED',['S1']),(f'Five {group}s passed.','CONTRADICTED',['S1']),(f'The test was easy.','UNKNOWN',[]),(f'No {group} passed.','CONTRADICTED',['S1'])]
        return pair,'INVARIANCE',(a,pa,0,'every_four'),(b,pb,0,'all_four')
    focus2=f'At least one {group} did not pass.'
    a=[f'Not every {group} passed.']
    b=[f'It is false that every {group} passed.']
    p=[(focus2,'ENTAILED',['S1']),(f'Every {group} passed.','CONTRADICTED',['S1']),(f'No {group} passed.','UNKNOWN',[]),(f'Some {group} passed.','UNKNOWN',[]),(f'At least one {group} exists.','ENTAILED',['S1']),(f'Exactly one {group} failed.','UNKNOWN',[]),(f'A {group} failed.','ENTAILED',['S1'])]
    return pair,'INVARIANCE',(a,p,0,'not_every_plain'),(b,p,0,'not_every_paraphrase')
