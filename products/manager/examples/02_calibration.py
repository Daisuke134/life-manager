"""L003 simple synthetic reliability diagram data, independent study holdout."""
from manager_core.calibration import reliability_bins, assert_disjoint_groups

if __name__=='__main__':
    assert_disjoint_groups(['study-a'], ['study-b'])
    result=reliability_bins([.5]*10,[0,1]*5)
    for x in result:
        if x['count']:
            print('SYNTHETIC holdout:',x)
    print('No field data, model accuracy certification or causal effect.')
