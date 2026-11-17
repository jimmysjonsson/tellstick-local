"""Print aggregate export coverage, never keys, device names, or RF code values."""
from pathlib import Path
import json
import sys


def audit(path):
    data=json.loads(Path(path).read_text())
    result={'complete_flag':data.get('complete',False), 'sections':{},
            'recorded_failures':len(data.get('failures',[])),
            'history_included':False, 'devices_with_rf_parameters':0}
    for name,section in data.get('sections',{}).items():
        details=section.get('details',[])
        successful=[item for item in details if 'failure' not in item.get('response',{})]
        result['sections'][name]={'saved_details':len(successful),'failed_details':len(details)-len(successful)}
        if name=='devices':
            for item in successful:
                response=item['response']
                if response.get('protocol') and response.get('model') and response.get('parameter'):
                    result['devices_with_rf_parameters']+=1
    result['all_configuration_sections_present']=set(result['sections'])=={'clients','devices','sensors','schedules','events'}
    result['complete_for_requested_scope']=bool(result['complete_flag'] and not result['recorded_failures'] and result['all_configuration_sections_present'])
    return result


if __name__=='__main__':
    print(json.dumps(audit(sys.argv[1]),indent=2))
